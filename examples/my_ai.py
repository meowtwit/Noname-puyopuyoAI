"""自作 AI のテンプレート。

    python -m puyo bench --ai examples.my_ai:MyAI -n 100
    python -m puyo play  --ai examples.my_ai:MyAI --seed 0 --open
"""

from puyo.ai import AI
from puyo.core import Move, simulate
from puyo.game import GameState


class MyAI(AI):
    name = "my_ai"

    def decide(self, state: GameState) -> Move:
        # state.field   : 現在のフィールド（Field。コピーなので自由に書き換えてよい）
        # state.current : 今操作する組ぷよ（Pair）
        # state.nexts   : (NEXT1, NEXT2)
        # state.hand    : 何手目か（0 始まり）
        # self.options  : --opt KEY=VALUE で渡したパラメータ
        best, best_score = None, None
        for move in state.legal_moves():
            field, chain, tear = simulate(state.field, state.current, move)
            if field.is_dead():
                continue
            score = self.evaluate(field) - tear * 10
            if best_score is None or score > best_score:
                best, best_score = move, score
        return best or state.legal_moves()[0]

    def evaluate(self, field) -> float:
        # TODO: ここに評価関数を書く
        return -max(field.heights())
