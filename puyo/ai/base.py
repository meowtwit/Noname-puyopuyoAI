from __future__ import annotations

from abc import ABC, abstractmethod

from ..core import Move
from ..game import GameState


class AI(ABC):
    """AI の基底クラス。decide() で置き方を 1 つ返す。

    - 1 ゲームごとに新しいインスタンスが作られる（状態を持ってよい）
    - seed はゲームごとに異なる値が渡される（乱数を使う AI 用）
    """

    name = "base"

    def __init__(self, seed: int = 0, **options):
        self.seed = seed
        self.options = options

    @abstractmethod
    def decide(self, state: GameState) -> Move: ...
