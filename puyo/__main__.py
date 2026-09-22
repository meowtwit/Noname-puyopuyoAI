"""コマンドライン:

  python -m puyo bench --ai greedy -n 200 -j 8     # とこぷよで AI を評価
  python -m puyo play  --ai greedy --seed 3        # 1 ゲーム実行してリプレイ HTML を出力
  python -m puyo sim "..RB..\n.RRBB." --pair RB --move 3^   # 盤面から 1 手シミュレーション
  python -m puyo tune  --ai beam_cpp --space beam --trials 30   # パラメータ自動調整（要 optuna）
  python -m puyo versus --ai1 versus_cpp --ai2 beam_cpp -n 100  # 対戦で勝率を測る
  python -m puyo vplay  --ai1 versus_cpp --ai2 beam_cpp --seed 0 --open   # 対戦 1 局のリプレイ
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from .bench import BenchConfig, format_summary, records_to_json, run_bench, run_game, summarize
from .core import Field, Move, Pair, simulate
from .replay import build_replay, write_replay
from .tsumo import TSUMO_MODES


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--ai", default="greedy", help="AI 名（random, greedy）または 'module:Class'")
    p.add_argument("--hands", type=int, default=50, help="最大手数（既定 50）")
    p.add_argument("--target", type=int, default=10, help="目標連鎖数（既定 10）")
    p.add_argument("--no-stop", action="store_true", help="目標連鎖を発火しても最大手数まで続ける")
    p.add_argument("--mode", default="ac", choices=TSUMO_MODES, help="ツモ生成方式（既定 ac）")
    p.add_argument("--nexts", type=int, default=2, help="AI に見せる NEXT の数（既定 2 = NEXT2 まで）")
    p.add_argument("--opt", action="append", default=[], metavar="KEY=VALUE", help="AI に渡すオプション（複数可）")


def _parse_opts(opts: list[str]) -> dict:
    out = {}
    for kv in opts:
        k, v = kv.split("=", 1)
        try:
            out[k] = json.loads(v)
        except json.JSONDecodeError:
            out[k] = v
    return out


def _config(a: argparse.Namespace, games: int = 1) -> BenchConfig:
    return BenchConfig(
        ai=a.ai,
        games=games,
        max_hands=a.hands,
        target_chain=a.target,
        stop_on_target=not a.no_stop,
        tsumo_mode=a.mode,
        visible_nexts=a.nexts,
        seed=a.seed,
        ai_options=_parse_opts(a.opt),
    )


def cmd_bench(a: argparse.Namespace) -> None:
    cfg = _config(a, a.games)
    t0 = time.perf_counter()
    records = run_bench(cfg, jobs=a.jobs)
    summary = summarize(cfg, records)
    print(format_summary(cfg, summary))
    print(f"  経過時間            : {time.perf_counter() - t0:.1f} s")
    errors = [r for r in records if r.error]
    if errors:
        print(f"\n最初のエラー (seed={errors[0].seed}):\n{errors[0].error}", file=sys.stderr)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(records_to_json(cfg, records, summary), ensure_ascii=False, indent=1))
        print(f"結果を保存: {a.out}")


def cmd_play(a: argparse.Namespace) -> None:
    cfg = _config(a)
    rec, game = run_game(cfg, a.seed, keep_history=True)
    if a.verbose:
        for st in game.history:
            tag = f"  {st.chain.chains}連鎖 {st.chain.score}点" if st.chain.chains else ""
            print(f"--- {st.hand + 1}手目 {st.pair} {st.move}{tag}")
            print(st.after)
    print(f"seed={a.seed} 手数={rec.hands} 最大{rec.max_chain}連鎖 ({rec.max_score}点) 累計{rec.total_score}点"
          + (" 窒息" if game.dead else ""))
    if rec.error:
        print(rec.error, file=sys.stderr)
    out = a.out or f"replays/{a.ai.replace(':', '_').replace('.', '_')}_seed{a.seed}.html"
    path = write_replay(build_replay(game, a.ai), out)
    print(f"リプレイ: {path}")
    if a.open:
        os.system(f"open '{path}'")


def cmd_sim(a: argparse.Namespace) -> None:
    field = Field.parse(a.field.replace("\\n", "\n"))
    pair = Pair.parse(a.pair)
    x, rot = int(a.move[0]), "^>v<".index(a.move[1])
    after, chain, tear = simulate(field, pair, Move(x, rot))
    print(f"before:\n{field}\n\nafter ({chain.chains}連鎖 {chain.score}点, ちぎり{tear}段):\n{after}")
    for s in chain.steps:
        print(f"  {s.chain}連鎖: {len(s.erased)}個消去 色数{s.colors} 連結{s.groups} → {s.score}点")


def cmd_tune(a: argparse.Namespace) -> None:
    from .tune import tune

    tune(
        _config(a, a.games),
        space_name=a.space,
        trials=a.trials,
        jobs=a.jobs,
        objective=a.objective,
        study_name=a.study or f"{a.ai}_{a.space}_t{a.target}",
        storage=a.storage,
        validate=a.validate,
        top=a.top,
    )


def _versus_config(a: argparse.Namespace):
    from .versus import MatchConfig, VersusRules

    rules = VersusRules(
        hand_frames=a.hand_frames, chain_frames=a.chain_frames, max_ojama_rows=a.max_rows,
        max_hands=a.max_hands, visible_nexts=a.nexts, tsumo_mode=a.mode,
    )
    return MatchConfig(a.ai1, a.ai2, _parse_opts(a.opt1), _parse_opts(a.opt2), getattr(a, "games", 1), a.seed, rules)


def cmd_versus(a: argparse.Namespace) -> None:
    from .versus import format_matches, run_matches

    cfg = _versus_config(a)
    t0 = time.perf_counter()
    rs = run_matches(cfg, jobs=a.jobs)
    print(format_matches(cfg, rs))
    print(f"  経過時間 {time.perf_counter() - t0:.1f} s")


def cmd_vplay_many(a: argparse.Namespace, cfg) -> None:
    from concurrent.futures import ProcessPoolExecutor

    from .replay import write_replays_home, write_versus_index
    from .versus import record_match

    tag = time.strftime("%Y%m%d_%H%M%S")
    outdir = Path(a.out or f"replays/versus_{cfg.ai1}_vs_{cfg.ai2}_{tag}")
    outdir.mkdir(parents=True, exist_ok=True)
    tasks = [(cfg, a.seed + i, str(outdir / f"seed{a.seed + i}.html")) for i in range(a.games)]
    with ProcessPoolExecutor(max_workers=a.jobs) as ex:
        entries = list(ex.map(record_match, tasks))
    names = (f"{cfg.ai1} {cfg.opts1 or ''}".strip(), f"{cfg.ai2} {cfg.opts2 or ''}".strip())
    index = write_versus_index(entries, names, f"対戦リプレイ一覧（{tag}）", outdir / "index.html")
    wins = sum(e["winner"] == 0 for e in entries)
    home = write_replays_home(outdir.parent)
    print(f"{len(entries)} 局のリプレイ: {index}  （ai1 の {wins} 勝）\nリプレイ置き場: {home}")
    if a.open:
        os.system(f"open '{index}'")


def cmd_vplay(a: argparse.Namespace) -> None:
    from .replay import write_versus_replay
    from .versus import play_match

    cfg = _versus_config(a)
    if a.games > 1:
        return cmd_vplay_many(a, cfg)
    r = play_match(cfg, a.seed, record=True)
    names = [f"{cfg.ai1}（ai1）", f"{cfg.ai2}（ai2）"]
    result = "引き分け" if r.winner is None else f"{names[r.winner]} の勝ち"
    print(f"seed={a.seed} {result}（{r.reason}） 手数 {r.hands}  時間 {r.time / 60:.1f} 秒")
    for i in range(2):
        s = r.stats[i]
        print(f"  {names[i]}: 最大{s.max_chain}連鎖  送った{s.sent}  受けた{s.received}  発火{s.fires}回")
    if r.error:
        print(r.error, file=sys.stderr)
    out = a.out or f"replays/versus_{cfg.ai1}_vs_{cfg.ai2}_seed{a.seed}.html"
    path = write_versus_replay(r.replay, out)
    print(f"リプレイ: {path}")
    if a.open:
        os.system(f"open '{path}'")


def _add_versus_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--ai1", default="versus_cpp")
    p.add_argument("--ai2", default="beam_cpp")
    p.add_argument("--opt1", action="append", default=[], metavar="KEY=VALUE", help="ai1 のオプション")
    p.add_argument("--opt2", action="append", default=[], metavar="KEY=VALUE", help="ai2 のオプション")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--mode", default="ac", choices=TSUMO_MODES)
    p.add_argument("--nexts", type=int, default=2)
    p.add_argument("--hand-frames", type=int, default=40, help="1 手にかかるフレーム")
    p.add_argument("--chain-frames", type=int, default=60, help="連鎖 1 段にかかるフレーム")
    p.add_argument("--max-rows", type=int, default=6, help="おじゃまが 1 回に降る最大段数")
    p.add_argument("--max-hands", type=int, default=250, help="この手数で引き分け")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m puyo", description="ぷよぷよ AI 試験環境")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("bench", help="とこぷよで AI を評価する")
    _add_common(b)
    b.add_argument("-n", "--games", type=int, default=100)
    b.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 1)
    b.add_argument("--seed", type=int, default=0, help="最初のシード（seed, seed+1, ... を使う）")
    b.add_argument("-o", "--out", help="結果 JSON の保存先")
    b.set_defaults(func=cmd_bench)

    p = sub.add_parser("play", help="1 ゲーム実行してリプレイを出力する")
    _add_common(p)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("-o", "--out", help="出力先（.html または .json）")
    p.add_argument("-v", "--verbose", action="store_true", help="毎手のフィールドを表示")
    p.add_argument("--open", action="store_true", help="出力した HTML をブラウザで開く")
    p.set_defaults(func=cmd_play)

    s = sub.add_parser("sim", help="盤面に 1 手置いて連鎖をシミュレーションする")
    s.add_argument("field", help="上の段から。行区切りは / か \\n（例: '..RB../.RRBB.'）")
    s.add_argument("--pair", required=True, help="組ぷよ（軸→子の順、例: RB）")
    s.add_argument("--move", required=True, help="軸の列と向き（^ > v <）例: 3^")
    s.set_defaults(func=cmd_sim)

    t = sub.add_parser("tune", help="AI のパラメータを自動調整する（Optuna）")
    _add_common(t)
    t.add_argument("--space", required=True, help="探索空間: eval / lookahead / beam / mcts（puyo/tune.py）")
    t.add_argument("--trials", type=int, default=30)
    t.add_argument("-n", "--games", type=int, default=100, help="1 試行あたりのゲーム数")
    t.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 1)
    t.add_argument("--seed", type=int, default=0)
    t.add_argument("--objective", default="safe", choices=["safe", "rate", "chain", "score"])
    t.add_argument("--study", help="スタディ名（同じ名前で再開できる）")
    t.add_argument("--storage", default="results/optuna.db", help="試行履歴の SQLite（空文字でメモリのみ）")
    t.add_argument("--validate", type=int, default=300, help="検証に使うゲーム数")
    t.add_argument("--top", type=int, default=3, help="検証する上位の数")
    t.set_defaults(func=cmd_tune)

    v = sub.add_parser("versus", help="2 つの AI を対戦させて勝率を測る")
    _add_versus_common(v)
    v.add_argument("-n", "--games", type=int, default=100)
    v.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 1)
    v.set_defaults(func=cmd_versus)

    vp = sub.add_parser("vplay", help="対戦のリプレイ HTML を出力する（-n で複数局＋一覧ページ）")
    _add_versus_common(vp)
    vp.add_argument("-n", "--games", type=int, default=20, help="局数（既定 20。1 なら 1 局だけ）")
    vp.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 1)
    vp.add_argument("-o", "--out", help="出力先（1 局ならファイル、複数ならディレクトリ）")
    vp.add_argument("--open", action="store_true")
    vp.set_defaults(func=cmd_vplay)

    a = ap.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
