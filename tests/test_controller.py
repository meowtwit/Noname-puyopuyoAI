import random

from puyo.controller import Controller, plan_operations
from puyo.core import ALL_MOVES, Field, Move


def col_field(heights):
    """列の高さだけ決めた盤面（色は連鎖しないように縦に交互）。"""
    cols = ["".join("RGBY"[(i + x) % 4] for i in range(h)) for x, h in enumerate(heights)]
    return Field.from_json(cols)


def test_empty_field_all_reachable():
    ops = plan_operations(Field())
    assert set(ops) == set(ALL_MOVES)
    assert ops[Move(3, 0)].keys == "" and ops[Move(3, 0)].frames == 2 * 11 + 20
    assert ops[Move(1, 0)].keys == "LL"
    # 6 列目で右回転すると壁蹴りで軸が 5 列目へ
    assert Controller([0] * 6).rotate(6, 12, 0, 1) == (5, 12, 1)


def test_column_of_12_blocks_axis_at_row_12():
    f = col_field([0, 12, 3, 0, 0, 0])
    ops = plan_operations(f)
    assert not any(m.x == 1 or m.child_x == 1 for m in ops)  # 1 列目へは行けない
    assert Move(4, 0) in ops


def test_climb_over_with_mawashi():
    # 自分の列（3 列目）が 11 段なら、床蹴りで登って 12 段の 2 列目を越えられる
    f = col_field([0, 12, 11, 0, 0, 0])
    ops = plan_operations(f)
    op = ops[Move(1, 0)]
    assert "A" in op.keys or "B" in op.keys
    x, y, r = Controller(f.heights()).apply(op.keys)
    assert (x, r) == (1, 0) and y >= 13


def test_quick_turn_between_full_columns():
    f = col_field([0, 13, 0, 13, 0, 0])
    ops = plan_operations(f)
    assert set(ops) == {Move(3, 0), Move(3, 2)}
    assert ops[Move(3, 2)].keys == "Q"


def test_keys_lead_to_the_move_on_random_fields():
    rng = random.Random(0)
    for _ in range(300):
        h = [rng.choice([0, 3, 8, 10, 11, 12, 13]) for _ in range(6)]
        h[2] = min(h[2], 11)  # 出現位置は空けておく
        c = Controller(h)
        for m, op in c.plan().items():
            x, y, r = c.apply(op.keys)
            assert (x, r) == (m.x, m.rot)
            assert op.frames >= 20


def test_row14_puyo_blocks_climbing():
    # 13 段の 2 列目を越えるには 14 段目を通る必要がある:
    # 4 列目（12 段）で床蹴りして軸を 14 段目へ上げ、14 段目を通って 1 列目へ
    h = [0, 13, 11, 12, 0, 0]
    ops = Controller(h).plan()
    assert Move(1, 1) in ops
    x, y, r = Controller(h).apply(ops[Move(1, 1)].keys)
    assert (x, y, r) == (1, 14, 1)
    # 4 列目の 14 段目にぷよが残っていると床蹴りで上がれず、行けない
    assert Move(1, 1) not in Controller(h, [False, False, False, True, False, False]).plan()
