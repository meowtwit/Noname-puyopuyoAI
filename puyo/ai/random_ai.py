from __future__ import annotations

import random

from ..core import Move
from ..game import GameState
from .base import AI


class RandomAI(AI):
    """合法手からランダムに選ぶ（下限の比較用）。"""

    name = "random"

    def __init__(self, seed: int = 0, **options):
        super().__init__(seed, **options)
        self.rng = random.Random(seed)

    def decide(self, state: GameState) -> Move:
        return self.rng.choice(state.legal_moves())
