"""lookahead の C++ 版（puyo/_puyocpp）。Python 版と同じオプション・同じ手を選び、数十〜数百倍速い。

ビルド: python scripts/build_cpp.py
"""

from __future__ import annotations

from ..core import Move
from ..game import GameState
from .base import AI

try:
    from .. import _puyocpp
except ImportError as e:  # pragma: no cover
    raise ImportError("C++ モジュールが未ビルドです。`python scripts/build_cpp.py` を実行してください") from e


class LookaheadCppAI(AI):
    name = "lookahead_cpp"

    def __init__(self, seed: int = 0, **options):
        super().__init__(seed, **options)
        self.impl = _puyocpp.LookaheadAI({k: float(v) for k, v in options.items()})

    def decide(self, state: GameState) -> Move:
        pairs = [str(state.current), *(str(p) for p in state.nexts)]
        hands_left = -1 if state.hands_left is None else state.hands_left
        x, rot = self.impl.decide(state.field.to_json(), pairs, hands_left)
        return Move(x, rot)
