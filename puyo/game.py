"""とこぷよ（1 人用の連鎖練習モード）のゲーム進行。"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field

from .core import ChainResult, Field, Move, Pair, simulate
from .tsumo import TsumoGenerator


@dataclass(frozen=True)
class GameState:
    """AI に渡す観測。field はコピーなので AI が書き換えても影響しない。"""

    field: Field
    current: Pair
    nexts: tuple[Pair, ...]  # 見えている NEXT（既定で NEXT1, NEXT2）
    hand: int  # 0 始まりの手数
    score: int  # これまでの累計得点
    hands_left: int | None = None  # 残り手数（今の手を含む）。無制限なら None

    def legal_moves(self) -> list[Move]:
        return self.field.legal_moves(self.current)


@dataclass
class StepResult:
    hand: int
    pair: Pair
    move: Move
    placed: Field  # 設置直後（連鎖前）
    after: Field  # 連鎖後
    chain: ChainResult
    tear: int  # ちぎり段差
    dead: bool
    think_ms: float = 0.0


@dataclass
class Tokopuyo:
    seed: int
    tsumo_mode: str = "ac"
    visible_nexts: int = 2
    max_hands: int | None = None
    field: Field = dc_field(default_factory=Field)
    hand: int = 0
    score: int = 0
    dead: bool = False
    history: list[StepResult] = dc_field(default_factory=list)

    def __post_init__(self) -> None:
        self.tsumo = TsumoGenerator(self.seed, self.tsumo_mode)

    def state(self) -> GameState:
        return GameState(
            field=self.field.copy(),
            current=self.tsumo.get(self.hand),
            nexts=tuple(self.tsumo.get(self.hand + i + 1) for i in range(self.visible_nexts)),
            hand=self.hand,
            score=self.score,
            hands_left=None if self.max_hands is None else self.max_hands - self.hand,
        )

    def step(self, move: Move) -> StepResult:
        if self.dead:
            raise RuntimeError("game is over")
        pair = self.tsumo.get(self.hand)
        if not self.field.is_reachable(move):
            raise IllegalMove(f"hand {self.hand}: move {move} is not reachable")
        placed = self.field.copy()
        placed.place(pair, move)
        after, chain, tear = simulate(self.field, pair, move)
        self.field = after
        self.score += chain.score
        self.dead = after.is_dead()
        res = StepResult(self.hand, pair, move, placed, after, chain, tear, self.dead)
        self.history.append(res)
        self.hand += 1
        return res


class IllegalMove(Exception):
    pass
