from collections import Counter

import pytest

from puyo.core import ALL_MOVES, Color, Field, Move, Pair, moves_for, simulate
from puyo.game import IllegalMove, Tokopuyo
from puyo.tsumo import TsumoGenerator


def test_parse_roundtrip():
    text = ".RBGY.\nRBGYR.\nRBGYR.\nRBGYRO"
    f = Field.parse(text)
    assert str(f) == text
    assert f.get(1, 1) == Color.RED and f.get(6, 1) == Color.OJAMA
    assert f.heights() == [3, 4, 4, 4, 4, 1]
    assert Field.from_json(f.to_json()) == f


def test_move_count():
    assert len(ALL_MOVES) == 22
    assert len(moves_for(Pair.parse("RR"))) == 11


def test_single_erase_score():
    f = Field.parse("R.....\nR.....\nR.....")
    after, chain, _ = simulate(f, Pair.parse("RB"), Move(1, 0))
    assert chain.chains == 1 and chain.score == 40
    assert str(after) == "B....."


def test_connection_and_color_bonus():
    # 5 連結: 10*5*2 = 100
    f = Field.parse("RRRR..")
    _, chain, _ = simulate(f, Pair.parse("RG"), Move(5, 1))
    assert chain.score == 10 * 5 * 2
    # 2 色同時: 10*8*3 = 240
    f = Field.parse("RRR...\nGGG...")
    _, chain, _ = simulate(f, Pair.parse("RG"), Move(4, 2))  # 子(G)が下、軸(R)が上
    assert chain.chains == 1 and chain.score == 10 * 8 * 3


def test_book_stairs_five_chain():
    """書籍 4.3 の階段 5 連鎖。"""
    f = Field.parse("ORBYG.\nRBYGR.\nRBYGR.\nRBYGRR")
    res = f.resolve_chain()
    assert res.chains == 5
    assert res.score == 40 + 320 + 640 + 1280 + 2560
    assert f.is_empty()  # 最後の R と隣接するおじゃまも消える


def test_row13_does_not_erase():
    # 1 列目の 10〜13 段目が R。13 段目は連鎖に参加しないので 3 個扱いで消えない
    rows = ["R....."] * 4 + [("B....." if y % 2 else "G.....") for y in range(9)]
    f = Field.parse("\n".join(rows))
    assert f.height(1) == 13
    assert f.resolve_chain().chains == 0


def test_row13_puyo_falls_into_chain():
    f = Field.parse(
        "\n".join(
            ["Y....."]  # 13 段目
            + ["R....."]  # 12 段目
            + ["B....." if y % 2 else "G....." for y in range(10, 0, -1)]  # 11..2 段目
            + ["GGG..."]  # 1 段目
        )
    )
    assert f.height(1) == 13
    # 1 段目の G に G を足して消す → 1 列目が 1 段下がって 13 段目の Y が 12 段目へ
    after, chain, _ = simulate(f, Pair.parse("GB"), Move(4, 0))
    assert chain.chains >= 1
    assert after.height(1) == 12 and after.get(1, 12) == Color.YELLOW


def test_ojama_erased_when_adjacent():
    f = Field.parse("O.....\nR.....\nR.....\nRO....")
    after, chain, _ = simulate(f, Pair.parse("RB"), Move(2, 1))  # 軸 R を 2 列目、子 B を 3 列目
    # (2,2) に R が置かれ 4 連結 → 隣接する (2,1) と (1,4) のおじゃまも消える
    assert chain.chains == 1
    assert after.count(Color.OJAMA) == 0


def test_tear():
    f = Field.parse("B.....\nB.....\nG.....")
    placed = f.copy()
    assert placed.place(Pair.parse("RY"), Move(1, 1)) == 3
    assert placed.get(1, 4) == Color.RED and placed.get(2, 1) == Color.YELLOW


def test_vertical_placement_order():
    f = Field()
    f.place(Pair.parse("RB"), Move(2, 0))
    assert f.get(2, 1) == Color.RED and f.get(2, 2) == Color.BLUE
    f = Field()
    f.place(Pair.parse("RB"), Move(2, 2))
    assert f.get(2, 1) == Color.BLUE and f.get(2, 2) == Color.RED


def test_row14_puyo_stays_and_never_falls():
    # 1 列目が 13 段。1〜2 列目に横置きすると、1 列目のぷよは 14 段目に入って残る
    f = Field.parse("\n".join(("B" if y % 2 else "G") + "....." for y in range(13)))
    assert f.height(1) == 13
    f.place(Pair.parse("RY"), Move(1, 1))
    assert f.get(1, 14) == Color.RED and f.height(1) == 13 and f.get(2, 1) == Color.YELLOW
    assert Field.from_json(f.to_json()) == f and f.to_json()[0].endswith("R") and len(f.to_json()[0]) == 14
    # 14 段目も埋まっている列に来たぷよは消える
    g = f.copy()
    g.place(Pair.parse("GG"), Move(1, 1))
    assert g.get(1, 14) == Color.RED and g.count() == f.count() + 1
    # 下が消えても 14 段目のぷよは落ちない
    h = Field.parse("R....." + "\n" + "\n".join("B....." if y % 2 else "Y....." for y in range(12)) + "\nGGG...")
    h.cols[0][0] = Color.GREEN  # 1 段目 1 列目を G にして GGG + G で消えるように
    assert h.get(1, 14) == Color.RED
    after, chain, _ = simulate(h, Pair.parse("GB"), Move(4, 0))
    assert chain.chains >= 1 and after.height(1) == 12 and after.get(1, 14) == Color.RED
    assert after.get(1, 13) == Color.EMPTY  # 13 段目は空いたが、14 段目のぷよは落ちてこない


def test_reachability_and_death():
    full = "\n".join(("B" if y % 2 else "G") + ("Y" if y % 2 else "R") + "...." for y in range(13))
    f = Field.parse(full)
    assert f.height(2) == 13
    assert not f.is_reachable(Move(1, 0))  # 2 列目が 13 段埋まっていて越えられない
    assert f.is_reachable(Move(4, 0))
    g = Tokopuyo(seed=0)
    g.field = f
    with pytest.raises(IllegalMove):
        g.step(Move(1, 0))
    dead = Field.parse("\n".join(("..B..." if y % 2 else "..G...") for y in range(11)))
    g = Tokopuyo(seed=0)
    g.field = dead
    assert not g.field.is_dead()
    g.step(Move(3, 1))
    assert g.dead


def test_tsumo_ac_balanced_and_reproducible():
    gen = TsumoGenerator(seed=42, mode="ac")
    pairs = [gen.get(i) for i in range(128)]
    cnt = Counter(c for p in pairs for c in (p.axis, p.child))
    assert set(cnt.values()) == {64}
    opening = {c for p in pairs[:3] for c in (p.axis, p.child)}
    assert len(opening) <= 3
    gen2 = TsumoGenerator(seed=42, mode="ac")
    assert [gen2.get(i) for i in range(200)] == [gen.get(i) for i in range(200)]


def test_tsumo_classic16_balanced():
    gen = TsumoGenerator(seed=1, mode="classic16", opening_three_color_hands=0)
    for k in range(4):
        block = [gen.get(i) for i in range(16 * k, 16 * (k + 1))]
        cnt = Counter(c for p in block for c in (p.axis, p.child))
        assert set(cnt.values()) == {8}


def test_detect_triggers_finds_book_stairs():
    from puyo.detect import detect_triggers

    f = Field.parse("ORBYG./RBYGR./RBYGR./RBYGR.")
    best = max(detect_triggers(f), key=lambda t: t.chains)
    assert (best.x, best.color, best.need, best.chains) == (6, Color.RED, 1, 5)
    assert f == Field.parse("ORBYG./RBYGR./RBYGR./RBYGR.")  # 元の盤面は変更しない
