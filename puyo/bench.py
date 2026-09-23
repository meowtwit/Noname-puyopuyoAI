"""とこぷよによる AI の評価。

書籍（4.5 評価関数の評価）の方法に準拠:
  とこぷよを走らせ、自滅 / 規定手数経過 / 目標連鎖の発火 のいずれかで終了し、
  発火した連鎖の最大値を記録する。多数のシードで回し、中央値で比較する。
"""

from __future__ import annotations

import statistics
import sys
import time
import traceback
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass

from .ai import load_ai_class
from .game import Tokopuyo


@dataclass
class BenchConfig:
    ai: str = "greedy"
    games: int = 100
    max_hands: int = 50
    target_chain: int = 10
    stop_on_target: bool = True
    tsumo_mode: str = "ac"
    visible_nexts: int = 2
    seed: int = 0
    ai_options: dict | None = None


@dataclass
class GameRecord:
    seed: int
    max_chain: int
    max_score: int
    total_score: int
    hands: int
    died: bool
    target_hand: int | None  # 目標連鎖を発火した手（0 始まり）。未達なら None
    zenkeshi_early: bool  # 8 手以内に全消し（書籍では評価から除外）
    think_ms_total: float
    error: str | None = None


def run_game(cfg: BenchConfig, game_seed: int, keep_history: bool = False) -> tuple[GameRecord, Tokopuyo]:
    ai = load_ai_class(cfg.ai)(seed=game_seed, **(cfg.ai_options or {}))
    game = Tokopuyo(
        seed=game_seed, tsumo_mode=cfg.tsumo_mode, visible_nexts=cfg.visible_nexts, max_hands=cfg.max_hands,
        record_ops=keep_history,
    )
    max_chain = max_score = 0
    target_hand = None
    zenkeshi_early = False
    think_total = 0.0
    error = None
    while game.hand < cfg.max_hands and not game.dead:
        state = game.state()
        t0 = time.perf_counter()
        try:
            move = ai.decide(state)
            think = (time.perf_counter() - t0) * 1000
            res = game.step(move)
        except Exception:
            error = traceback.format_exc(limit=3)
            break
        res.think_ms = think
        think_total += think
        if res.chain.chains > max_chain or (res.chain.chains == max_chain and res.chain.score > max_score):
            max_chain, max_score = res.chain.chains, res.chain.score
        if res.chain.chains and res.after.is_empty() and res.hand < 8:
            zenkeshi_early = True
        if res.chain.chains >= cfg.target_chain and target_hand is None:
            target_hand = res.hand
            if cfg.stop_on_target:
                break
    if not keep_history:
        game.history.clear()
    rec = GameRecord(
        seed=game_seed,
        max_chain=max_chain,
        max_score=max_score,
        total_score=game.score,
        hands=game.hand,
        died=game.dead or error is not None,
        target_hand=target_hand,
        zenkeshi_early=zenkeshi_early,
        think_ms_total=think_total,
        error=error,
    )
    return rec, game


def _run_one(args: tuple[BenchConfig, int]) -> GameRecord:
    cfg, seed = args
    return run_game(cfg, seed)[0]


def run_bench(cfg: BenchConfig, jobs: int = 1, progress: bool | None = None) -> list[GameRecord]:
    if progress is None:
        progress = sys.stdout.isatty()
    seeds = [cfg.seed + i for i in range(cfg.games)]
    tasks = [(cfg, s) for s in seeds]
    records: list[GameRecord] = []
    if jobs <= 1:
        it = map(_run_one, tasks)
        pool = None
    else:
        pool = ProcessPoolExecutor(max_workers=jobs)
        it = pool.map(_run_one, tasks)
    try:
        for i, rec in enumerate(it, 1):
            records.append(rec)
            if progress:
                print(f"\r  {i}/{cfg.games} games", end="", flush=True)
    finally:
        if pool:
            pool.shutdown()
    if progress:
        print()
    return records


@dataclass
class Summary:
    games: int
    evaluated: int
    success_rate: float  # 目標連鎖を発火できた割合
    median_max_chain: float
    mean_max_chain: float
    median_max_score: float
    death_rate: float
    mean_target_hand: float | None
    ms_per_move: float
    errors: int
    chain_hist: dict[int, int]


def summarize(cfg: BenchConfig, records: list[GameRecord]) -> Summary:
    rs = [r for r in records if not r.zenkeshi_early] or records
    chains = [r.max_chain for r in rs]
    hit = [r for r in rs if r.target_hand is not None]
    moves = sum(r.hands for r in records) or 1
    return Summary(
        games=len(records),
        evaluated=len(rs),
        success_rate=len(hit) / len(rs),
        median_max_chain=statistics.median(chains),
        mean_max_chain=statistics.fmean(chains),
        median_max_score=statistics.median(r.max_score for r in rs),
        death_rate=sum(r.died for r in rs) / len(rs),
        mean_target_hand=statistics.fmean(r.target_hand + 1 for r in hit) if hit else None,
        ms_per_move=sum(r.think_ms_total for r in records) / moves,
        errors=sum(r.error is not None for r in records),
        chain_hist=dict(sorted(Counter(chains).items())),
    )


def format_summary(cfg: BenchConfig, s: Summary) -> str:
    lines = [
        f"AI: {cfg.ai}  tsumo={cfg.tsumo_mode}  NEXT表示={cfg.visible_nexts}  "
        f"最大{cfg.max_hands}手  目標{cfg.target_chain}連鎖",
        f"  ゲーム数            : {s.games}（評価対象 {s.evaluated}）",
        f"  {cfg.target_chain}連鎖以上 発火率   : {s.success_rate * 100:.1f}%",
        f"  最大連鎖 中央値     : {s.median_max_chain}",
        f"  最大連鎖 平均       : {s.mean_max_chain:.2f}",
        f"  最大得点 中央値     : {s.median_max_score:.0f}",
        f"  窒息率              : {s.death_rate * 100:.1f}%",
        f"  目標到達までの平均手数: {s.mean_target_hand:.1f}" if s.mean_target_hand else "  目標到達までの平均手数: -",
        f"  思考時間            : {s.ms_per_move:.2f} ms/手",
    ]
    if s.errors:
        lines.append(f"  !! AI エラー        : {s.errors} ゲーム")
    total = sum(s.chain_hist.values())
    lines.append("  最大連鎖の分布:")
    for chain, n in s.chain_hist.items():
        bar = "#" * max(1, round(40 * n / total)) if n else ""
        lines.append(f"    {chain:2d}連鎖 {n:4d} {bar}")
    return "\n".join(lines)


def records_to_json(cfg: BenchConfig, records: list[GameRecord], summary: Summary) -> dict:
    return {"config": asdict(cfg), "summary": asdict(summary), "games": [asdict(r) for r in records]}


def record_game(args) -> dict:
    """1 ゲームを記録してリプレイ HTML を書き出し、一覧ページ用の要約を返す（並列実行用）。"""
    from pathlib import Path

    from .replay import build_replay, write_replay

    cfg, seed, out = args
    rec, game = run_game(cfg, seed, keep_history=True)
    write_replay(build_replay(game, cfg.ai), out)
    fires = [(st.hand + 1, st.chain.chains, st.chain.score) for st in game.history if st.chain.chains]
    return {"file": Path(out).name, "seed": seed, "max_chain": rec.max_chain, "max_score": rec.max_score,
            "hands": rec.hands, "died": rec.died, "target_hand": rec.target_hand, "fires": fires}
