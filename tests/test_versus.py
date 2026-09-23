"""対戦エンジン（puyo/versus.py）のテスト。ツモと置き方を固定した台本 AI で確かめる。"""

from puyo.ai.base import AI
from puyo.core import Field, Move, Pair
from puyo.versus import VersusGame, VersusRules

STAIRS = "ORBYG./RBYGR./RBYGR./RBYGR."  # RR を 6 列目に縦置きで 5 連鎖・4900 点 = おじゃま 70 個
FILLER = ["GB", "YR", "BG", "RY"]
COLS = [1, 2, 4, 5, 6]


class Script(AI):
    """手数ごとに決めた手を打つ。決めていない手は列を順番に回して縦置き。"""

    name = "script"

    def __init__(self, moves=None, cols=COLS):
        super().__init__()
        self.moves = moves or {}
        self.cols = cols

    def decide(self, state):
        return self.moves.get(state.hand, Move(self.cols[state.hand % len(self.cols)], 0))


def make_game(ai0, ai1, field0="", field1="", first="RR", max_hands=14, use_controller=False):
    # タイミングを確かめるテストは 1 手 40f 固定のモードで行う
    rules = VersusRules(max_hands=max_hands, use_controller=use_controller, hand_frames=40)
    g = VersusGame((ai0, ai1), seed=0, rules=rules)
    g.tsumo._pairs = [Pair.parse(first)] + [Pair.parse(FILLER[i % 4]) for i in range(40)]
    if field0:
        g.players[0].field = Field.parse(field0)
    if field1:
        g.players[1].field = Field.parse(field1)
    return g


def test_ojama_falls_after_first_hand_placed_after_chain_ends():
    g = make_game(Script({0: Move(6, 0)}), Script(), field0=STAIRS)
    r = g.run()
    fires = [e for e in r.events if e[2] == "fire"]
    drops = [e for e in r.events if e[2] == "drop"]
    assert [(e[1], e[3], e[4]) for e in fires] == [(0, 5, 70)]
    # 連鎖は 40 + 5 × 60 = 340 フレームで終わる。相手が 340 以降に置き始めた手（360 開始 → 400 に置き終わる）の後に降る
    assert drops[0][:4] == (400, 1, "drop", 36)
    assert drops[1][1:4] == (1, "drop", 34)  # 1 回に最大 6 段（36 個）。残りは次の手の後
    assert r.stats[1].received == 70 and r.stats[1].fires == 0


def test_simultaneous_chains_offset_each_other():
    g = make_game(Script({0: Move(6, 0)}), Script({0: Move(6, 0)}), field0=STAIRS, field1=STAIRS)
    r = g.run()
    assert [e[3] for e in r.events if e[2] == "fire"] == [5, 5]
    assert not [e for e in r.events if e[2] == "drop"]  # 同じ量なので全部相殺
    assert g.players[0].incoming == g.players[1].incoming == 0
    assert r.stats[0].sent == r.stats[1].sent == 70


def test_player_who_fills_column3_loses():
    g = make_game(Script(), Script(cols=[3]), max_hands=40)
    r = g.run()
    assert r.winner == 0 and r.reason == "dead"
    assert r.hands[1] == 6  # 3 列目に縦置き 6 手で 12 段目が埋まる


def test_versus_info_window():
    """相手の連鎖中は、終わるまでに置ける手数＋ 1 手が猶予になる。"""
    seen = []

    class Watch(Script):
        def decide(self, state):
            v = state.versus
            seen.append((v.now, v.incoming_total, v.window, v.opp_chaining))
            return super().decide(state)

    make_game(Script({0: Move(6, 0)}), Watch(), field0=STAIRS).run()
    # t=40: 相手の連鎖は 340 まで → 40, 80, ..., 320 開始の 8 手 ＋ 終わった後の 1 手 = 9 手
    t40 = next(s for s in seen if s[0] == 40)
    assert t40 == (40, 70, 9, True)
    t360 = next(s for s in seen if s[0] == 360)
    assert t360[2] == 1 and not t360[3]


def test_versus_cpp_options_and_short_match():
    import pytest

    pytest.importorskip("puyo._puyocpp")
    from puyo.versus import MatchConfig, VersusRules, play_match

    rules = VersusRules(max_hands=12)
    small = {"width": 6, "samples": 2, "depth": 4}
    for opts in ({}, {"crush": 1, "crush_check": 0, "crush_until": 8, "residual": 0}):
        cfg = MatchConfig("versus_cpp", "beam_cpp", {**small, **opts}, dict(small), rules=rules)
        r = play_match(cfg, 1)
        assert r.error is None and r.reason in ("max_hands", "dead")


def test_hand_time_follows_operation_frames():
    """操作時間モードでは、1 手の時間 = 実際の操作（キー入力＋落下＋接地＋ちぎり）のフレーム。"""
    from puyo.controller import plan_operations

    times = []

    class Watch(Script):
        def decide(self, state):
            times.append((state.versus.now, state.field.copy(), self.moves.get(state.hand, Move(1, 0))))
            return times[-1][2]

    make_game(Watch({0: Move(1, 0), 1: Move(6, 1), 2: Move(3, 2)}), Script(cols=[5]), max_hands=4,
              use_controller=True).run()
    for (t0, f, m), (t1, _, _) in zip(times, times[1:]):
        assert t1 - t0 == plan_operations(f)[m].frames
    assert times[1][0] == plan_operations(Field())[Move(1, 0)].frames == 2 * 2 + 2 * 11 + 20  # ←← と 11 段落下
