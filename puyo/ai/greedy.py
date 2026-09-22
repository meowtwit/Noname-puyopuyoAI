from __future__ import annotations

from ..core import Move, simulate
from ..game import GameState
from .base import AI


class GreedyAI(AI):
    """1 手読みの貪欲 AI（動作確認用のベースライン）。

    連鎖が起きる手があれば得点最大の手、なければ死なずにフィールドが低く平らになる手を選ぶ。
    """

    name = "greedy"

    def decide(self, state: GameState) -> Move:
        best, best_key = None, None
        for move in state.legal_moves():
            f, chain, tear = simulate(state.field, state.current, move)
            if f.is_dead():
                key = (-1, 0, 0)
            else:
                hs = f.heights()
                key = (1, chain.score, -(max(hs) - min(hs)) - tear)
            if best_key is None or key > best_key:
                best, best_key = move, key
        return best
