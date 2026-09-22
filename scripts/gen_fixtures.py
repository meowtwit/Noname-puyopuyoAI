"""Python 版の実装から C++ セルフテスト用の正解データ（tests/fixtures/cpp_fixtures.txt）を作る。

    python scripts/gen_fixtures.py

形式は cpp/tools/selftest.cpp の冒頭を参照。Python 側のルールや lookahead を変えたら作り直す。
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from puyo.ai.lookahead import LookaheadAI  # noqa: E402
from puyo.core import Field, simulate  # noqa: E402
from puyo.detect import detect_triggers  # noqa: E402
from puyo.game import Tokopuyo  # noqa: E402


def cols(f: Field) -> str:
    return " ".join(c or "-" for c in f.to_json())


def random_states(seed: int, hands: int):
    """ランダムに置いて作った（安定した）盤面と、その時の組ぷよ列。"""
    rng = random.Random(seed)
    g = Tokopuyo(seed=seed, max_hands=hands)
    out = []
    while g.hand < hands and not g.dead:
        st = g.state()
        out.append(st)
        legal = st.legal_moves()
        safe = [m for m in legal if not simulate(st.field, st.current, m)[0].is_dead()]
        g.step(rng.choice(safe or legal))
    return out


def ai_states(seed: int, hands: int):
    """Python 版 lookahead で実際に打った盤面（連鎖の種が多い）。"""
    ai = LookaheadAI()
    g = Tokopuyo(seed=seed, max_hands=hands)
    out = []
    while g.hand < hands and not g.dead:
        st = g.state()
        mv = ai.decide(st)
        out.append((st, mv))
        g.step(mv)
    return out


def main() -> None:
    lines: list[str] = []
    states = [s for seed in range(40) for s in random_states(seed, 40)]
    played = [x for seed in (100, 101, 102) for x in ai_states(seed, 45)]
    ai = LookaheadAI()

    for i, st in enumerate(states + [s for s, _ in played]):
        f = st.field
        for m in f.legal_moves(st.current) if i % 4 == 0 else ():
            after, chain, tear = simulate(f, st.current, m)
            lines.append(f"S {cols(f)} {st.current} {m.x} {m.rot} {cols(after)} {chain.chains} {chain.score} {tear}")
        trig = sorted((t.x, t.color.char, t.need, t.chains, t.score) for t in detect_triggers(f))
        lines.append(f"D {cols(f)} {len(trig)} " + " ".join(f"{x} {c} {n} {ch} {sc}" for x, c, n, ch, sc in trig))

    # lookahead の判断: 実戦の盤面 + ランダム盤面（窒息寸前など）+ 残り手数が少ない場面
    decide_cases = [(st, mv) for st, mv in played]
    for st in states[::15]:
        decide_cases.append((st, ai.decide(st)))
    for st, _ in played[::9]:
        st2 = st.__class__(**{**st.__dict__, "hands_left": 2})
        decide_cases.append((st2, ai.decide(st2)))
    for st, mv in decide_cases:
        pairs = [st.current, *st.nexts]
        hl = -1 if st.hands_left is None else st.hands_left
        lines.append(f"L {cols(st.field)} {len(pairs)} {' '.join(map(str, pairs))} {hl} {mv.x} {mv.rot}")

    out = ROOT / "tests" / "fixtures" / "cpp_fixtures.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    n = {k: sum(ln.startswith(k) for ln in lines) for k in "SDL"}
    print(f"wrote {out} (simulate {n['S']}, detect {n['D']}, lookahead {n['L']})")


if __name__ == "__main__":
    main()
