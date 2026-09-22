from puyo.ai import load_ai_class
from puyo.bench import BenchConfig, run_game
from puyo.core import Field, Pair
from puyo.game import GameState


def _state(field, pairs, hands_left=None):
    ps = [Pair.parse(p) for p in pairs]
    return GameState(field=field, current=ps[0], nexts=tuple(ps[1:]), hand=10, score=0, hands_left=hands_left)


def test_lookahead_fires_when_target_reached():
    ai = load_ai_class("lookahead")(fire=5)
    f = Field.parse("ORBYG./RBYGR./RBYGR./RBYGR.")
    move = ai.decide(_state(f, ["RR", "GB", "YY"]))
    assert move.x == 6  # 6 列目に R を置いて 5 連鎖


def test_lookahead_keeps_small_chain():
    ai = load_ai_class("lookahead")(fire=10)
    f = Field.parse("ORBYG./RBYGR./RBYGR./RBYGR.")
    move = ai.decide(_state(f, ["RR", "GB", "YY"]))
    assert move.x != 6 and move.child_x != 6  # 5 連鎖は撃たずに温存する


def test_lookahead_fires_at_last_hand():
    ai = load_ai_class("lookahead")(fire=10)
    f = Field.parse("ORBYG./RBYGR./RBYGR./RBYGR.")
    move = ai.decide(_state(f, ["RR", "GB", "YY"], hands_left=1))
    assert move.x == 6


def test_builtin_ais_run():
    for name in ("random", "greedy", "lookahead"):
        rec, _ = run_game(BenchConfig(ai=name, max_hands=8), game_seed=1)
        assert rec.error is None and rec.hands == 8
