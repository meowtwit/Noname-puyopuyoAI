"""AI のパラメータ自動調整（Optuna / TPE）。

  python -m puyo tune --ai beam_cpp --space beam --trials 30 -n 100 --target 14 --hands 60 \\
      --opt fire=14 --opt width=20 --opt samples=4        # --opt で渡したものは固定（探索しない）

- 全試行で同じシード（--seed から n 個）を使い、パラメータの差だけを比べる（ばらつきを抑える）
- 1 試行目は既定値（+ --opt）なので、調整後が既定値より悪くなることはない（学習用シード上では）
- 最後に上位 --top 個と既定値を、学習に使っていない別のシード（--validate 個）で再評価して過学習を確認する
- 結果は results/tune_<study>.json、試行の履歴は --storage（既定 results/optuna.db）に残り、同じ --study で再開できる

目的関数（--objective）:
  safe   目標連鎖の発火率 − 窒息率（既定。発火率だけだと「死んでもいいから一発狙い」に寄る）
  rate   目標連鎖の発火率（同率なら最大連鎖の平均が大きい方）
  chain  最大連鎖の平均
  score  最大得点の平均
"""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import replace
from pathlib import Path

from .bench import BenchConfig, run_bench, summarize

# 探索空間: 名前 → (下限, 上限, 対数スケールか, 整数か)
EVAL_SPACE = {
    "w_need": (50, 800, True, False),
    "conn2": (0, 60, False, False),
    "conn3": (0, 150, False, False),
    "w_shape": (1, 30, True, False),
    "w_block": (200, 5000, True, False),
}
SPACES = {
    "eval": EVAL_SPACE,
    "lookahead": {**EVAL_SPACE, "danger": (48, 66, False, True), "w_tear": (0, 50, False, False)},
    "beam": {**EVAL_SPACE, "small_fire": (0.0, 1.0, False, False)},
    "mcts": {
        **EVAL_SPACE,
        "c": (0.2, 4.0, True, False),
        "pw_k": (1.0, 4.0, False, False),
        "pw_alpha": (0.2, 0.7, False, False),
        "small_fire": (0.0, 1.0, False, False),
    },
}
# 既定値（C++ / Python の既定と同じ。1 試行目に使う）
DEFAULTS = {
    "w_need": 250, "conn2": 10, "conn3": 30, "w_shape": 8, "w_block": 1500,
    "danger": 54, "w_tear": 5, "c": 1.0, "pw_k": 2.0, "pw_alpha": 0.5,
}  # fmt: skip
SMALL_FIRE_DEFAULT = {"beam": 1.0, "mcts": 0.1}


def objective_value(kind: str, cfg: BenchConfig, records) -> float:
    s = summarize(cfg, records)
    if kind == "safe":
        return s.success_rate - s.death_rate + s.mean_max_chain / 1000
    if kind == "rate":
        return s.success_rate + s.mean_max_chain / 1000
    if kind == "chain":
        return s.mean_max_chain
    if kind == "score":
        return statistics.fmean(r.max_score for r in records)
    raise ValueError(f"unknown objective: {kind}")


def evaluate(base: BenchConfig, params: dict, seed: int, games: int, jobs: int, objective: str):
    cfg = replace(base, seed=seed, games=games, ai_options={**(base.ai_options or {}), **params})
    records = run_bench(cfg, jobs=jobs, progress=False)
    return objective_value(objective, cfg, records), summarize(cfg, records)


def tune(
    base: BenchConfig,
    space_name: str,
    trials: int,
    jobs: int,
    objective: str = "safe",
    study_name: str = "study",
    storage: str | None = "results/optuna.db",
    validate: int = 300,
    top: int = 3,
) -> dict:
    import optuna

    # --opt で固定したものは探索しない
    space = {k: v for k, v in SPACES[space_name].items() if k not in (base.ai_options or {})}
    defaults = {k: DEFAULTS.get(k, SMALL_FIRE_DEFAULT.get(space_name, 1.0)) for k in space}

    if storage:
        Path(storage).parent.mkdir(parents=True, exist_ok=True)
        storage = f"sqlite:///{storage}"
    else:
        storage = None
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(
        study_name=study_name,
        storage=storage,
        load_if_exists=True,
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=base.seed, multivariate=True),
    )
    if not study.trials:
        study.enqueue_trial(defaults)

    def run_trial(trial: optuna.Trial) -> float:
        params = {}
        for k, (lo, hi, log, is_int) in space.items():
            params[k] = trial.suggest_int(k, lo, hi) if is_int else trial.suggest_float(k, lo, hi, log=log)
        t0 = time.perf_counter()
        value, s = evaluate(base, params, base.seed, base.games, jobs, objective)
        trial.set_user_attr("summary", {"rate": s.success_rate, "mean_chain": s.mean_max_chain,
                                        "median_chain": s.median_max_chain, "death": s.death_rate})
        print(f"  trial {trial.number:3d}: {objective}={value:.4f}  発火率={s.success_rate * 100:5.1f}%  "
              f"平均{s.mean_max_chain:5.2f}連鎖  窒息{s.death_rate * 100:4.1f}%  ({time.perf_counter() - t0:.0f}s)",
              flush=True)
        return value

    print(f"調整: {base.ai}  空間={space_name}（{', '.join(space)}）  目的={objective}  "
          f"{base.games}ゲーム/試行  目標{base.target_chain}連鎖  最大{base.max_hands}手")
    study.optimize(run_trial, n_trials=trials)

    # 別シードで上位と既定値を再評価
    done = [t for t in study.trials if t.value is not None]
    ranked = sorted(done, key=lambda t: t.value, reverse=True)[:top]
    candidates = [("既定値", defaults)] + [(f"trial {t.number}", t.params) for t in ranked]
    val_seed = base.seed + 1_000_000
    print(f"\n検証（学習に使っていないシード {val_seed}〜、{validate} ゲーム）:")
    results = []
    for name, params in candidates:
        value, s = evaluate(base, params, val_seed, validate, jobs, objective)
        results.append({"name": name, "params": params, "value": value, "rate": s.success_rate,
                        "mean_chain": s.mean_max_chain, "median_chain": s.median_max_chain, "death": s.death_rate})
        print(f"  {name:10s}: {objective}={value:.4f}  発火率={s.success_rate * 100:5.1f}%  "
              f"平均{s.mean_max_chain:5.2f}連鎖  中央値{s.median_max_chain}  窒息{s.death_rate * 100:.1f}%")
    best = max(results, key=lambda r: r["value"])
    opt_str = " ".join(f"--opt {k}={_fmt(v)}" for k, v in {**(base.ai_options or {}), **best["params"]}.items())
    print(f"\n最良: {best['name']}\n  {opt_str}")

    out = {"config": base.__dict__, "space": space_name, "objective": objective, "validation": results,
           "best": best, "opt": opt_str}
    path = Path("results") / f"tune_{study_name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    print(f"結果を保存: {path}")
    return out


def _fmt(v) -> str:
    return str(v) if isinstance(v, int) else f"{v:.4g}"
