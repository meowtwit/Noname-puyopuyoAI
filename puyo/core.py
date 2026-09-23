"""ぷよぷよ通ルールのコア実装（フィールド・組ぷよ・設置・連鎖シミュレーション・得点計算）。

座標系は「第１回ぷよぷよ人類vsAI」の表記に合わせる:
  - 列 x は左から 1..6、段 y は下から 1..13
  - (3, 12) が埋まると窒息（ゲームオーバー）
  - 13 段目のぷよは見えているが連鎖には参加しない
  - 14 段目（画面外）に置いたぷよは残り続け、下が消えても落ちず、消えもしない（通の仕様）。
    13 段目まで埋まった列に来たぷよは 14 段目に入り、14 段目も埋まっていれば消える
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

WIDTH = 6
HEIGHT = 13  # 重力で詰まる段数（13 段目まで）
TOP_ROW = 14  # 画面外の 14 段目（置いたぷよは落ちずに残る）
VISIBLE_HEIGHT = 12  # 連鎖判定に参加する段数
DEATH_X, DEATH_Y = 3, 12
SPAWN_X = 3


class Color(IntEnum):
    EMPTY = 0
    RED = 1
    GREEN = 2
    BLUE = 3
    YELLOW = 4
    OJAMA = 5

    @property
    def char(self) -> str:
        return _COLOR_TO_CHAR[self]

    @classmethod
    def from_char(cls, c: str) -> Color:
        return _CHAR_TO_COLOR[c.upper()]

    @property
    def is_normal(self) -> bool:
        return Color.RED <= self <= Color.YELLOW


_COLOR_TO_CHAR = {
    Color.EMPTY: ".",
    Color.RED: "R",
    Color.GREEN: "G",
    Color.BLUE: "B",
    Color.YELLOW: "Y",
    Color.OJAMA: "O",
}
_CHAR_TO_COLOR = {v: k for k, v in _COLOR_TO_CHAR.items()}
NORMAL_COLORS = (Color.RED, Color.GREEN, Color.BLUE, Color.YELLOW)

# ぷよぷよ通の得点ボーナス
CHAIN_BONUS = [0, 8, 16, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448, 480, 512]
CONNECTION_BONUS = {4: 0, 5: 2, 6: 3, 7: 4, 8: 5, 9: 6, 10: 7}  # 11 以上は 10
COLOR_BONUS = [0, 0, 3, 6, 12, 24]


def chain_bonus(chain: int) -> int:
    return CHAIN_BONUS[min(chain, len(CHAIN_BONUS)) - 1]


def connection_bonus(size: int) -> int:
    return CONNECTION_BONUS.get(size, 10 if size >= 11 else 0)


# ---------------------------------------------------------------------------
# 組ぷよと操作
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pair:
    """組ぷよ。axis が軸ぷよ、child が子ぷよ（初期状態で軸の上にある）。"""

    axis: Color
    child: Color

    def __str__(self) -> str:
        return f"{self.axis.char}{self.child.char}"

    @classmethod
    def parse(cls, s: str) -> Pair:
        return cls(Color.from_char(s[0]), Color.from_char(s[1]))

    @property
    def is_double(self) -> bool:
        return self.axis == self.child


@dataclass(frozen=True)
class Move:
    """置き方。x は軸ぷよの列 (1..6)、rot は子ぷよの向き。

    rot: 0=上, 1=右, 2=下, 3=左
    """

    x: int
    rot: int

    @property
    def child_x(self) -> int:
        return self.x + (1 if self.rot == 1 else -1 if self.rot == 3 else 0)

    def __str__(self) -> str:
        return f"{self.x}{'^>v<'[self.rot]}"


ALL_MOVES: tuple[Move, ...] = tuple(
    Move(x, rot)
    for x in range(1, WIDTH + 1)
    for rot in range(4)
    if 1 <= Move(x, rot).child_x <= WIDTH
)  # 22 通り


def moves_for(pair: Pair) -> tuple[Move, ...]:
    """組ぷよに対する、結果が重複しない置き方の候補（ゾロなら 11 通り）。"""
    if pair.is_double:
        return tuple(m for m in ALL_MOVES if m.rot in (0, 1))
    return ALL_MOVES


# ---------------------------------------------------------------------------
# 連鎖結果
# ---------------------------------------------------------------------------


@dataclass
class ChainStep:
    chain: int
    erased: list[tuple[int, int]]  # 消えたぷよの座標（おじゃま含む）
    colors: int
    groups: list[int]  # 消えた各連結のサイズ
    score: int


@dataclass
class ChainResult:
    chains: int = 0
    score: int = 0
    steps: list[ChainStep] = field(default_factory=list)

    @property
    def erased_count(self) -> int:
        return sum(len(s.erased) for s in self.steps)


# ---------------------------------------------------------------------------
# フィールド
# ---------------------------------------------------------------------------


class Field:
    """6 列のフィールド。1〜13 段目は列ごとに下からのリスト（重力で常に詰まっている）、
    14 段目は top に別に持つ（落ちずに残るため）。"""

    __slots__ = ("cols", "top")

    def __init__(self, cols: list[list[Color]] | None = None, top: list[Color] | None = None):
        self.cols: list[list[Color]] = cols if cols is not None else [[] for _ in range(WIDTH)]
        self.top: list[Color] = top if top is not None else [Color.EMPTY] * WIDTH

    # --- 生成・入出力 -------------------------------------------------------

    @classmethod
    def parse(cls, text: str) -> Field:
        """書籍の表記（上の段から、R/G/B/Y/O/.）からフィールドを作る。

        上部の空行は省略可。各行は 6 文字で、改行か "/" で区切る。浮いているぷよは下に落とす。
        14 行あれば 1 行目が 14 段目（落ちずにその場に残る）。
        """
        lines = [ln.strip() for ln in text.replace("/", "\n").strip().splitlines() if ln.strip()]
        if len(lines) > TOP_ROW:
            raise ValueError(f"too many rows: {len(lines)}")
        f = cls()
        for y, line in enumerate(reversed(lines), start=1):
            if len(line) != WIDTH:
                raise ValueError(f"row must have {WIDTH} chars: {line!r}")
            for i, c in enumerate(line):
                color = Color.from_char(c)
                if color == Color.EMPTY:
                    continue
                if y == TOP_ROW:
                    f.top[i] = color
                else:
                    f.cols[i].append(color)
        return f

    def copy(self) -> Field:
        return Field([list(c) for c in self.cols], list(self.top))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Field) and self.cols == other.cols and self.top == other.top

    def __hash__(self) -> int:
        return hash((tuple(tuple(c) for c in self.cols), tuple(self.top)))

    def to_rows(self, height: int = TOP_ROW) -> list[str]:
        rows = []
        for y in range(height, 0, -1):
            rows.append("".join(self.get(x, y).char for x in range(1, WIDTH + 1)))
        return rows

    def __str__(self) -> str:
        rows = self.to_rows()
        while rows and rows[0] == "." * WIDTH:
            rows.pop(0)
        return "\n".join(rows) if rows else "." * WIDTH

    def to_json(self) -> list[str]:
        """列ごとの文字列（下から）。14 段目にぷよがあれば 13 文字目まで "." で埋めて 14 文字目に色。"""
        out = []
        for col, top in zip(self.cols, self.top):
            s = "".join(c.char for c in col)
            if top != Color.EMPTY:
                s = s.ljust(HEIGHT, ".") + top.char
            out.append(s)
        return out

    @classmethod
    def from_json(cls, data: list[str]) -> Field:
        f = cls()
        for i, s in enumerate(data):
            if len(s) > HEIGHT:
                f.top[i] = Color.from_char(s[HEIGHT])
                s = s[:HEIGHT]
            f.cols[i] = [Color.from_char(c) for c in s.rstrip(".")]
        return f

    # --- 参照 ---------------------------------------------------------------

    def get(self, x: int, y: int) -> Color:
        if y == TOP_ROW:
            return self.top[x - 1]
        col = self.cols[x - 1]
        return col[y - 1] if y <= len(col) else Color.EMPTY

    def height(self, x: int) -> int:
        return len(self.cols[x - 1])

    def heights(self) -> list[int]:
        return [len(c) for c in self.cols]

    def count(self, color: Color | None = None) -> int:
        if color is None:
            return sum(len(c) for c in self.cols) + sum(t != Color.EMPTY for t in self.top)
        return sum(c.count(color) for c in self.cols) + self.top.count(color)

    def is_dead(self) -> bool:
        return self.height(DEATH_X) >= DEATH_Y

    def is_empty(self) -> bool:
        return all(not c for c in self.cols) and all(t == Color.EMPTY for t in self.top)

    # --- 設置 ---------------------------------------------------------------

    def is_reachable(self, move: Move) -> bool:
        """組ぷよを実際の操作（移動・回転・壁蹴り・床蹴り・クイックターン）でその位置まで運べるか。

        詳しくは puyo/controller.py。12 段以上の列が無ければどこでも置ける。
        """
        from .controller import reachable_moves

        return move in reachable_moves(self)

    def legal_moves(self, pair: Pair) -> list[Move]:
        from .controller import reachable_moves

        ok = reachable_moves(self)
        return [m for m in moves_for(pair) if m in ok]

    def place(self, pair: Pair, move: Move) -> int:
        """組ぷよを置く（連鎖はしない）。ちぎりが発生した段差を返す（0 ならちぎり無し）。"""
        if move not in ALL_MOVES:
            raise ValueError(f"invalid move: {move}")
        if move.rot == 2:  # 子が下
            self._drop(move.x, pair.child)
            self._drop(move.x, pair.axis)
            return 0
        if move.rot == 0:
            self._drop(move.x, pair.axis)
            self._drop(move.x, pair.child)
            return 0
        h_axis, h_child = self.height(move.x), self.height(move.child_x)
        self._drop(move.x, pair.axis)
        self._drop(move.child_x, pair.child)
        return abs(h_axis - h_child)

    def _drop(self, x: int, color: Color) -> None:
        col = self.cols[x - 1]
        if len(col) < HEIGHT:
            col.append(color)
        elif self.top[x - 1] == Color.EMPTY:
            self.top[x - 1] = color  # 14 段目に入って残る
        # 14 段目も埋まっていれば消える

    def drop_ojama(self, n: int, rng=None) -> None:
        """おじゃまぷよを n 個降らせる（6 個ごとに 1 段、端数はランダムな列）。"""
        import random

        rng = rng or random
        rows, rest = divmod(n, WIDTH)
        for _ in range(rows):
            for x in range(1, WIDTH + 1):
                self._drop(x, Color.OJAMA)
        for x in rng.sample(range(1, WIDTH + 1), rest):
            self._drop(x, Color.OJAMA)

    # --- 連鎖 ---------------------------------------------------------------

    def find_erasable(self) -> tuple[list[tuple[int, int]], int, list[int]]:
        """4 つ以上つながった色ぷよと、それに隣接するおじゃまを探す。

        戻り値: (消える座標, 色数, 各連結のサイズ)
        """
        visited = [[False] * (VISIBLE_HEIGHT + 1) for _ in range(WIDTH + 1)]
        erase: set[tuple[int, int]] = set()
        colors: set[Color] = set()
        groups: list[int] = []
        cols = self.cols
        for x in range(1, WIDTH + 1):
            col = cols[x - 1]
            for y in range(1, min(len(col), VISIBLE_HEIGHT) + 1):
                if visited[x][y]:
                    continue
                color = col[y - 1]
                if not color.is_normal:
                    continue
                stack = [(x, y)]
                visited[x][y] = True
                group = []
                while stack:
                    cx, cy = stack.pop()
                    group.append((cx, cy))
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if 1 <= nx <= WIDTH and 1 <= ny <= VISIBLE_HEIGHT and not visited[nx][ny]:
                            ncol = cols[nx - 1]
                            if ny <= len(ncol) and ncol[ny - 1] == color:
                                visited[nx][ny] = True
                                stack.append((nx, ny))
                if len(group) >= 4:
                    erase.update(group)
                    colors.add(color)
                    groups.append(len(group))
        if not erase:
            return [], 0, []
        # 隣接するおじゃまぷよ
        ojama = set()
        for cx, cy in erase:
            for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if 1 <= nx <= WIDTH and 1 <= ny <= VISIBLE_HEIGHT and self.get(nx, ny) == Color.OJAMA:
                    ojama.add((nx, ny))
        return sorted(erase | ojama), len(colors), groups

    def _remove(self, positions: list[tuple[int, int]]) -> None:
        by_col: dict[int, set[int]] = {}
        for x, y in positions:
            by_col.setdefault(x, set()).add(y)
        for x, ys in by_col.items():
            col = self.cols[x - 1]
            self.cols[x - 1] = [c for i, c in enumerate(col, start=1) if i not in ys]

    def connects4(self, x: int, y: int) -> bool:
        """(x, y) の色ぷよが 4 つ以上つながっているか（12 段目まで）。"""
        cols = self.cols
        if y > VISIBLE_HEIGHT or y > len(cols[x - 1]):
            return False
        color = cols[x - 1][y - 1]
        if not color.is_normal:
            return False
        seen = {(x, y)}
        stack = [(x, y)]
        while stack:
            cx, cy = stack.pop()
            for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if 1 <= nx <= WIDTH and 1 <= ny <= VISIBLE_HEIGHT and (nx, ny) not in seen:
                    ncol = cols[nx - 1]
                    if ny <= len(ncol) and ncol[ny - 1] == color:
                        seen.add((nx, ny))
                        if len(seen) >= 4:
                            return True
                        stack.append((nx, ny))
        return False

    def resolve_chain(self) -> ChainResult:
        """連鎖を最後まで進め、結果を返す（フィールドは破壊的に更新される）。"""
        result = ChainResult()
        while True:
            erased, n_colors, groups = self.find_erasable()
            if not erased:
                return result
            result.chains += 1
            n_normal = sum(groups)
            bonus = chain_bonus(result.chains) + sum(connection_bonus(g) for g in groups) + COLOR_BONUS[n_colors]
            score = 10 * n_normal * max(1, bonus)
            result.score += score
            result.steps.append(ChainStep(result.chains, erased, n_colors, groups, score))
            self._remove(erased)


def simulate(field: Field, pair: Pair, move: Move) -> tuple[Field, ChainResult, int]:
    """非破壊で設置→連鎖まで行う。(新フィールド, 連鎖結果, ちぎり段差) を返す。"""
    f = field.copy()
    tear = f.place(pair, move)
    # 高速化: 置いたぷよが 4 つ以上つながらなければ連鎖は起きない
    x, cx = move.x, move.child_x
    if x == cx:
        h = f.height(x)
        fires = f.connects4(x, h) or f.connects4(x, h - 1)
    else:
        fires = f.connects4(x, f.height(x)) or f.connects4(cx, f.height(cx))
    return f, (f.resolve_chain() if fires else ChainResult()), tear
