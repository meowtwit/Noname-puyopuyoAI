"""見えているツモ（手持ち + NEXT）だけで発火できる最大連鎖を評価する AI。

各候補手について:
  1. その手を置いた後、残りの見えている組ぷよで打てる最大の連鎖（ポテンシャル）を全探索で求める
  2. ポテンシャル（連鎖数を主、得点を従）＋形の評価 で点を付け、最大の手を選ぶ

発火の判断:
  - 今の手で fire 連鎖以上が打てるなら撃つ
  - それ未満の連鎖は撃たない（連鎖を壊すため）。ポテンシャルとして温存して伸ばす
  - ただし窒息が近い / 残り手数が見えている範囲で尽きるときは、打てる最大の連鎖を撃つ

オプション（--opt KEY=VALUE）:
  fire     撃つ連鎖数の閾値（既定 10）
  w_chain  ポテンシャル 1 連鎖あたりの点（既定 1000）
  conn2    2 連結 1 つあたりの点（既定 10）
  conn3    3 連結 1 つあたりの点（既定 30）
  w_shape  理想形（U 字）からのずれ²の係数（既定 8）
  w_tear   ちぎり 1 段あたりの減点（既定 5）
  danger   この個数以上ぷよがあれば危険とみなす（既定 54）
"""

from __future__ import annotations

from ..core import VISIBLE_HEIGHT, WIDTH, Color, Field, Move, Pair, simulate
from ..game import GameState
from .base import AI

NEG_INF = float("-inf")

# U 字の理想形（平均高さからのずれ）。端を高く、3・4 列目を低く
U_SHAPE = (2.0, 0.5, -1.0, -1.0, 0.0, 1.5)


class LookaheadAI(AI):
    name = "lookahead"

    def __init__(self, seed: int = 0, **options):
        super().__init__(seed, **options)
        o = options
        self.fire = int(o.get("fire", 10))
        self.w_chain = float(o.get("w_chain", 1000))
        self.conn2 = float(o.get("conn2", 10))
        self.conn3 = float(o.get("conn3", 30))
        self.w_shape = float(o.get("w_shape", 8))
        self.w_tear = float(o.get("w_tear", 5))
        self.danger = int(o.get("danger", 54))

    # ------------------------------------------------------------------

    def decide(self, state: GameState) -> Move:
        pairs = [state.current, *state.nexts]
        if state.hands_left is not None:
            pairs = pairs[: max(1, state.hands_left)]
        # 見えている範囲で手数が尽きる / 窒息が近いなら、小さくても撃ってよい
        free_fire = (state.hands_left is not None and state.hands_left <= len(pairs)) or self.in_danger(state.field)

        best_move, best_val = None, NEG_INF
        for move in state.legal_moves():
            f1, chain, tear = simulate(state.field, state.current, move)
            if f1.is_dead():
                continue
            if chain.chains:
                if chain.chains >= self.fire:
                    val = 1e9 + chain.score  # 目標到達。即発火
                elif free_fire:
                    val = self.chain_value(chain.chains, chain.score)
                else:
                    val = -1e6 + chain.score  # 小連鎖の暴発は避ける
            else:
                pc, ps = self.potential(f1, pairs[1:])
                val = self.chain_value(pc, ps) + self.shape(f1) - self.w_tear * tear
            if val > best_val:
                best_move, best_val = move, val
        return best_move or state.legal_moves()[0]

    def chain_value(self, chains: int, score: int) -> float:
        return self.w_chain * chains + score / 100

    def potential(self, field: Field, pairs: list[Pair]) -> tuple[int, int]:
        """残りの組ぷよを順に置いて打てる最大の連鎖 (連鎖数, 得点)。"""
        if not pairs:
            return 0, 0
        best = (0, 0)
        pair, rest = pairs[0], pairs[1:]
        for move in field.legal_moves(pair):
            f, chain, _ = simulate(field, pair, move)
            if f.is_dead():
                continue
            if chain.chains:
                cand = (chain.chains, chain.score)
            elif rest:
                cand = self.potential(f, rest)
            else:
                continue
            if cand > best:
                best = cand
        return best

    # ------------------------------------------------------------------

    def in_danger(self, field: Field) -> bool:
        return field.count() >= self.danger or field.height(3) >= 10

    def shape(self, field: Field) -> float:
        """形の評価: 同色の連結（2・3 連結）を加点、U 字からのずれを減点。"""
        score = 0.0
        cols = field.cols
        seen: set[tuple[int, int]] = set()
        for x in range(1, WIDTH + 1):
            col = cols[x - 1]
            for y in range(1, min(len(col), VISIBLE_HEIGHT) + 1):
                if (x, y) in seen or col[y - 1] == Color.OJAMA:
                    continue
                n = self._group_size(cols, x, y, seen)
                if n == 2:
                    score += self.conn2
                elif n >= 3:
                    score += self.conn3

        hs = field.heights()
        avg = sum(hs) / WIDTH
        score -= self.w_shape * sum((h - avg - u) ** 2 for h, u in zip(hs, U_SHAPE))
        return score

    @staticmethod
    def _group_size(cols, x: int, y: int, seen: set) -> int:
        color = cols[x - 1][y - 1]
        stack = [(x, y)]
        seen.add((x, y))
        n = 0
        while stack:
            cx, cy = stack.pop()
            n += 1
            for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if 1 <= nx <= WIDTH and 1 <= ny <= VISIBLE_HEIGHT and (nx, ny) not in seen:
                    ncol = cols[nx - 1]
                    if ny <= len(ncol) and ncol[ny - 1] == color:
                        seen.add((nx, ny))
                        stack.append((nx, ny))
        return n
