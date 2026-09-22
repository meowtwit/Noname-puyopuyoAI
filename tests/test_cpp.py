"""C++ 版（puyo/_puyocpp）が Python 版と同じ結果を返すことを確認する。未ビルドならスキップ。"""

import random
from pathlib import Path

import pytest

from puyo.ai.lookahead import LookaheadAI
from puyo.core import ALL_MOVES, Color, Field, Move, Pair, simulate
from puyo.detect import detect_triggers

cpp = pytest.importorskip("puyo._puyocpp", reason="C++ モジュール未ビルド（python scripts/build_cpp.py）")

FIXTURES = Path(__file__).parent / "fixtures" / "cpp_fixtures.txt"
COLORS = "RGBY"


def random_field(rng: random.Random) -> Field:
    """ランダムな高さ・色で埋めて連鎖させた、安定した盤面（おじゃま入り）。"""
    cols = []
    for _ in range(6):
        h = rng.randint(0, 13)
        cols.append("".join(rng.choice(COLORS + "O" if rng.random() < 0.1 else COLORS) for _ in range(h)))
    f = Field.from_json(cols)
    f.resolve_chain()
    return f


def test_simulate_matches_python():
    rng = random.Random(0)
    n_chain = 0
    for _ in range(3000):
        f = random_field(rng)
        pair = Pair(Color(rng.randint(1, 4)), Color(rng.randint(1, 4)))
        m = rng.choice(ALL_MOVES)
        after, chain, tear = simulate(f, pair, m)
        got = cpp.simulate(f.to_json(), str(pair), m.x, m.rot)
        assert got == (after.to_json(), chain.chains, chain.score, tear), (str(f), pair, m)
        n_chain += chain.chains > 0
    assert n_chain > 100  # 連鎖が起きるケースも十分含まれている


def test_resolve_chain_matches_python():
    rng = random.Random(1)
    for _ in range(2000):
        cols = ["".join(rng.choice(COLORS) for _ in range(rng.randint(0, 13))) for _ in range(6)]
        f = Field.from_json(cols)
        res = f.resolve_chain()
        assert cpp.resolve_chain(cols) == (f.to_json(), res.chains, res.score)


def test_detect_matches_python():
    rng = random.Random(2)
    for _ in range(500):
        f = random_field(rng)
        want = sorted((t.x, t.color.char, t.need, t.chains, t.score) for t in detect_triggers(f))
        assert sorted(cpp.detect(f.to_json())) == want


def test_lookahead_decisions_match_fixtures():
    ai = cpp.LookaheadAI()
    n = 0
    for line in FIXTURES.read_text().splitlines():
        if not line.startswith("L "):
            continue
        t = line.split()
        cols = [c if c != "-" else "" for c in t[1:7]]
        npairs = int(t[7])
        pairs = t[8 : 8 + npairs]
        hands_left, x, rot = map(int, t[8 + npairs : 11 + npairs])
        assert ai.decide(cols, pairs, hands_left) == (x, rot), line
        n += 1
    assert n > 100


def test_lookahead_options_are_passed():
    from puyo.game import GameState

    f = Field.parse("ORBYG./RBYGR./RBYGR./RBYGR.")
    st = GameState(field=f, current=Pair.parse("RR"), nexts=(Pair.parse("GB"), Pair.parse("YY")), hand=10, score=0)
    for opts in ({}, {"fire": 5}, {"detect_depth": 0}):
        py = LookaheadAI(**opts).decide(st)
        assert cpp.LookaheadAI({k: float(v) for k, v in opts.items()}).decide(f.to_json(), ["RR", "GB", "YY"], -1) == (
            py.x,
            py.rot,
        )
    with pytest.raises(Exception):
        cpp.LookaheadAI({"no_such_option": 1.0})


STAIRS = Field.parse("ORBYG./RBYGR./RBYGR./RBYGR.")


@pytest.mark.parametrize("cls", ["BeamAI", "MctsAI"])
def test_sampling_ai_basic(cls):
    small = {"BeamAI": {"width": 8, "samples": 2, "depth": 4}, "MctsAI": {"iterations": 200, "depth": 4}}[cls]
    Impl = getattr(cpp, cls)
    cols = STAIRS.to_json()
    pairs = ["RR", "GB", "YY"]
    # 目標（fire=5）に届く連鎖が撃てるなら即座に撃つ
    assert Impl({**small, "fire": 5.0}, 0).decide(cols, pairs, -1, None) == (6, 0)
    # 同じシードなら同じ手（再現性）、合法手を返す
    a = Impl(small, 7).decide(cols, pairs, -1, [60, 60, 60, 60])
    b = Impl(small, 7).decide(cols, pairs, -1, [60, 60, 60, 60])
    assert a == b
    assert Move(*a) in STAIRS.legal_moves(Pair.parse("RR"))
    # 最後の 1 手なら 5 連鎖でも撃つ
    assert Impl(small, 0).decide(cols, pairs, 1, None) == (6, 0)
    with pytest.raises(Exception):
        Impl({"no_such_option": 1.0}, 0)


def test_sampling_ai_tracks_ac_cycle():
    from puyo.ai.sampling_cpp import BeamCppAI
    from puyo.game import Tokopuyo

    ai = BeamCppAI(seed=0, width=4, samples=1, depth=3)
    g = Tokopuyo(seed=3)
    for _ in range(5):
        st = g.state()
        rem = ai.remaining(st)
        seen = [c for h in range(g.hand + 3) for p in [g.tsumo.get(h)] for c in (p.axis, p.child)]
        assert rem == [64 - seen.count(Color(i)) for i in range(1, 5)]
        g.step(ai.decide(st))
    assert BeamCppAI(seed=0, tsumo_model="uniform").remaining(g.state()) is None


def test_builtin_cpp_ais_run():
    from puyo.bench import BenchConfig, run_game

    for name, opts in (("beam_cpp", {"width": 6, "samples": 2, "depth": 4}), ("mcts_cpp", {"iterations": 100})):
        rec, _ = run_game(BenchConfig(ai=name, max_hands=10, ai_options=opts), game_seed=1)
        assert rec.error is None and rec.hands == 10
