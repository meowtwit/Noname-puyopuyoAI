"""ツモ（組ぷよ列）の生成。

- "ac"        : アーケード版ぷよぷよ通風。128 手（256 個）で 4 色が 64 個ずつ均等。
                開始 3 手は 3 色のみ。128 手を使い切ったら新しい周期を作る。
- "classic16" : ぷよぷよフィーバーのクラシック風。16 手ごとに 4 色均等。
- "random"    : 完全ランダム（偏り補正なし）。

いずれもシード固定で再現可能。
"""

from __future__ import annotations

import random

from .core import NORMAL_COLORS, Color, Pair

TSUMO_MODES = ("ac", "classic16", "random")


class TsumoGenerator:
    def __init__(self, seed: int, mode: str = "ac", opening_three_color_hands: int = 3):
        if mode not in TSUMO_MODES:
            raise ValueError(f"unknown tsumo mode: {mode} (choose from {TSUMO_MODES})")
        self.rng = random.Random(seed)
        self.mode = mode
        self.opening = opening_three_color_hands
        self._pairs: list[Pair] = []
        self._first_cycle = True

    def get(self, index: int) -> Pair:
        """index 手目（0 始まり）の組ぷよ。必要に応じて生成を進める。"""
        while len(self._pairs) <= index:
            self._pairs.extend(self._next_cycle())
        return self._pairs[index]

    def _next_cycle(self) -> list[Pair]:
        if self.mode == "random":
            puyos = [self.rng.choice(NORMAL_COLORS) for _ in range(256)]
        else:
            hands = 128 if self.mode == "ac" else 16
            puyos = [c for c in NORMAL_COLORS for _ in range(hands // 2)]
            self.rng.shuffle(puyos)
        if self._first_cycle and self.opening > 0:
            self._restrict_opening(puyos)
        self._first_cycle = False
        return [Pair(puyos[i], puyos[i + 1]) for i in range(0, len(puyos), 2)]

    def _restrict_opening(self, puyos: list[Color]) -> None:
        """開始 N 手を 3 色に制限する。全体の色数を保つため後方のぷよと入れ替える。"""
        n = min(self.opening * 2, len(puyos))
        allowed = set(self.rng.sample(NORMAL_COLORS, 3))
        for i in range(n):
            if puyos[i] in allowed:
                continue
            for j in range(n, len(puyos)):
                if puyos[j] in allowed:
                    puyos[i], puyos[j] = puyos[j], puyos[i]
                    break
            else:  # classic16 など周期が短い場合は置き換えで妥協
                puyos[i] = self.rng.choice(sorted(allowed))


def make_sequence(seed: int, n: int, mode: str = "ac") -> list[Pair]:
    gen = TsumoGenerator(seed, mode)
    return [gen.get(i) for i in range(n)]
