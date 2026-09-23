"""対戦で「打ち返し」がどれだけ成功しているかを集計する。

    python scripts/counter_stats.py --ai1 versus_cpp --ai2 versus_cpp -n 60 [--opt1 k=v ...]

打ち返し = おじゃまが 6 個を超えて来ている（相手の連鎖中を含む）ときに撃った連鎖。
成功 = 送ったおじゃま ≥ 来ていた量（全部相殺して送り返せた）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from puyo.__main__ import _parse_opts  # noqa: E402
from puyo.versus import MatchConfig, run_matches  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ai1", default="versus_cpp")
    ap.add_argument("--ai2", default="versus_cpp")
    ap.add_argument("--opt1", action="append", default=[])
    ap.add_argument("--opt2", action="append", default=[])
    ap.add_argument("-n", "--games", type=int, default=60)
    ap.add_argument("-j", "--jobs", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    cfg = MatchConfig(a.ai1, a.ai2, _parse_opts(a.opt1), _parse_opts(a.opt2), a.games, a.seed)
    rs = run_matches(cfg, jobs=a.jobs)
    for side in (0, 1):
        cs = [e for r in rs for e in r.events if e[2] == "fire" and e[1] == side and e[5] > 6]
        big = [e for e in cs if e[5] >= 200]  # 相手の本線（200 個以上）への打ち返し
        wins = sum(r.winner == side for r in rs)

        def rate(xs):
            return f"{sum(e[4] >= e[5] for e in xs)}/{len(xs)}" if xs else "-"

        diff = sum(e[4] - e[5] for e in big) / len(big) if big else 0
        win_after = []  # 本線への打ち返しをした試合の勝率
        for r in rs:
            if any(e[2] == "fire" and e[1] == side and e[5] >= 200 for e in r.events):
                win_after.append(r.winner == side)
        print(f"{'ai1' if side == 0 else 'ai2'}: 勝ち {wins}/{len(rs)}  打ち返し成功 {rate(cs)}  "
              f"本線への打ち返し成功 {rate(big)}（送った−来た 平均 {diff:+.0f}）  "
              f"本線に打ち返した試合の勝率 {sum(win_after)}/{len(win_after)}  "
              f"猶予 平均 {sum(e[6] for e in big) / max(1, len(big)):.1f} 手")


if __name__ == "__main__":
    main()
