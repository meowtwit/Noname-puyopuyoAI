"""連鎖の検出（書籍 3.4 RensaDetector の detectByDropStrategy 相当）。

各列の上に、周囲にある色のぷよを 1〜3 個足して消えるかを試し、
起きる連鎖（連鎖数・得点・足した個数）を列挙する。
"""

from __future__ import annotations

from dataclasses import dataclass

from .core import VISIBLE_HEIGHT, WIDTH, Color, Field


@dataclass(frozen=True)
class Trigger:
    x: int  # 足す列
    color: Color
    need: int  # 足したぷよの数
    chains: int
    score: int


def detect_triggers(field: Field, max_need: int = 3) -> list[Trigger]:
    """field に色ぷよを足して起こせる連鎖をすべて返す（field は変更しない）。"""
    out: list[Trigger] = []
    cols = field.cols
    for x in range(1, WIDTH + 1):
        h = len(cols[x - 1])
        if h >= VISIBLE_HEIGHT:
            continue
        # 足したぷよが接しうる位置の色だけ試す（離れた色を足しても連鎖は起きない）
        colors: set[Color] = set()
        if h:
            colors.add(cols[x - 1][h - 1])
        for nx in (x - 1, x + 1):
            if 1 <= nx <= WIDTH:
                ncol = cols[nx - 1]
                for y in range(h + 1, min(h + max_need, VISIBLE_HEIGHT) + 1):
                    if y <= len(ncol):
                        colors.add(ncol[y - 1])
        for color in colors:
            if not color.is_normal:
                continue
            f = field.copy()
            col = f.cols[x - 1]
            for k in range(1, max_need + 1):
                if h + k > VISIBLE_HEIGHT:
                    break
                col.append(color)
                if f.connects4(x, h + k):
                    res = f.resolve_chain()
                    out.append(Trigger(x, color, k, res.chains, res.score))
                    break
    return out
