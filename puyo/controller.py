"""操作列生成（組ぷよを実際のキー入力で目的の位置まで運ぶ）。

組ぷよの状態は「軸ぷよの位置 (x, y) と子ぷよの向き r」。r: 0=上, 1=右, 2=下, 3=左。
出現時は軸 (3, 12)・子 (3, 13)・r=0。移動中は 14 段目まで入れる（15 段目以上は天井）。
14 段目に残っているぷよのマスは通れない。

キー:
  L / R : 左右に 1 列。軸と子の行き先が両方空いていること
  A / B : 右回転 / 左回転。子の行き先が塞がっていたら蹴る:
          - 横向き（r=1, 3）になれない → 軸が反対側へ 1 列ずれる（壁蹴り）
          - 下向き（r=2）になれない → 軸が 1 段上がる（床蹴り。繰り返すと「回し」で高い列を登れる）
  Q     : クイックターン（回転キー 2 回）。左右とも塞がって回転できないとき、上下を入れ替える（必要なら軸が 1 段上がる）
最後に真下へ落として置く。

フレーム数（書籍の値を参考）: キー 1 回 2f、クイックターン 4f、落下 1 段 2f、接地 20f、
ちぎり +20f ＋ 離れたぷよの落下（1 段 10f、以降 1 段ごとに +6f）。

探索はスタート位置からのダイクストラ法（状態は 6 列 × 14 段 × 4 向き = 336 通り）。
AI の合法手（どこに置けるか）もこの結果に揃える。
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass

from .core import ALL_MOVES, WIDTH, Move

MAX_ROW = 14  # 移動中に入れる最も高い段
SPAWN = (3, 12, 0)
DX = (0, 1, 0, -1)
DY = (1, 0, -1, 0)

KEY_FRAMES = 2
QUICK_TURN_FRAMES = 4
DROP_FRAMES_PER_ROW = 2
LOCK_FRAMES = 20
TEAR_FRAMES = 20


def tear_fall_frames(rows: int) -> int:
    """ちぎれたぷよが rows 段落ちるのにかかるフレーム（1 段 10f、以降 +6f ずつ）。"""
    return 0 if rows <= 0 else 10 + 6 * (rows - 1)


@dataclass(frozen=True)
class Operation:
    move: Move
    keys: str  # 例 "LLA"（最後の落下は含まない）
    frames: int  # キー入力＋落下＋接地（＋ちぎり）

    def pretty(self) -> str:
        return pretty_keys(self.keys)


def pretty_keys(keys: str) -> str:
    table = {"L": "←", "R": "→", "A": "↻", "B": "↺", "Q": "⇅"}
    return "".join(table[k] for k in keys) + "↓"


class Controller:
    """盤面の高さから、置ける場所・キー列・フレーム数を求める。"""

    def __init__(self, heights: list[int], top: list[bool] | None = None):
        self.h = heights  # 列 1..6 の高さ（heights[0] が 1 列目。13 段目まで）
        self.top = top or [False] * WIDTH  # 14 段目にぷよが残っているか

    def free(self, x: int, y: int) -> bool:
        if not (1 <= x <= WIDTH and 1 <= y <= MAX_ROW and y > self.h[x - 1]):
            return False
        return not (y == MAX_ROW and self.top[x - 1])

    def valid(self, x: int, y: int, r: int) -> bool:
        return self.free(x, y) and self.free(x + DX[r], y + DY[r])

    def rotate(self, x: int, y: int, r: int, d: int):
        """d=+1 で右回転、-1 で左回転。回れなければ None。"""
        r2 = (r + d) % 4
        if self.valid(x, y, r2):
            return x, y, r2
        if r2 in (1, 3):  # 壁蹴り: 軸を反対側へ
            x2 = x - DX[r2]
            if self.valid(x2, y, r2):
                return x2, y, r2
        elif r2 == 2:  # 床蹴り: 軸を 1 段上へ
            if self.valid(x, y + 1, r2):
                return x, y + 1, r2
        return None

    def quick_turn(self, x: int, y: int, r: int):
        if r not in (0, 2) or self.rotate(x, y, r, 1) or self.rotate(x, y, r, -1):
            return None
        r2 = (r + 2) % 4
        if self.valid(x, y, r2):
            return x, y, r2
        if r2 == 2 and self.valid(x, y + 1, r2):
            return x, y + 1, r2
        return None

    def neighbors(self, s):
        x, y, r = s
        if self.valid(x - 1, y, r):
            yield "L", KEY_FRAMES, (x - 1, y, r)
        if self.valid(x + 1, y, r):
            yield "R", KEY_FRAMES, (x + 1, y, r)
        for key, d in (("A", 1), ("B", -1)):
            t = self.rotate(x, y, r, d)
            if t:
                yield key, KEY_FRAMES, t
        t = self.quick_turn(x, y, r)
        if t:
            yield "Q", QUICK_TURN_FRAMES, t

    def apply(self, keys: str, start=SPAWN):
        """キー列をなぞった後の状態。途中で動けなければ None。"""
        path = self.path(keys, start)
        return path[-1] if path else None

    def path(self, keys: str, start=SPAWN) -> list[tuple[int, int, int]] | None:
        """キー列をなぞった途中の状態（出現位置を含む）。途中で動けなければ None。"""
        s, out = start, [start]
        for k in keys:
            for key, _, t in self.neighbors(s):
                if key == k:
                    s = t
                    break
            else:
                return None
            out.append(s)
        return out

    def drop_frames(self, x: int, y: int, r: int) -> int:
        """(x, y, r) から真下に落として置くまでのフレーム（落下＋接地＋ちぎり）。"""
        cx = x + DX[r]
        if cx == x:
            low = min(y, y + DY[r])  # 下にあるぷよ
            fall = low - (self.h[x - 1] + 1)
            return fall * DROP_FRAMES_PER_ROW + LOCK_FRAMES
        ha, hc = self.h[x - 1], self.h[cx - 1]
        fall = y - (max(ha, hc) + 1)
        tear = abs(ha - hc)
        extra = TEAR_FRAMES + tear_fall_frames(tear) if tear else 0
        return fall * DROP_FRAMES_PER_ROW + LOCK_FRAMES + extra

    def plan(self) -> dict[Move, Operation]:
        """置ける場所ごとの最短の操作。出現位置が塞がっていれば空。"""
        if not self.valid(*SPAWN):
            return {}
        dist = {SPAWN: 0}
        keys = {SPAWN: ""}
        heap = [(0, SPAWN)]
        while heap:
            d, s = heapq.heappop(heap)
            if d > dist[s]:
                continue
            for key, cost, t in self.neighbors(s):
                nd = d + cost
                if nd < dist.get(t, 1 << 30) or (nd == dist.get(t) and keys[s] + key < keys[t]):
                    dist[t] = nd
                    keys[t] = keys[s] + key
                    heapq.heappush(heap, (nd, t))
        best: dict[Move, Operation] = {}
        for (x, y, r), d in dist.items():
            m = Move(x, r)
            total = d + self.drop_frames(x, y, r)
            cur = best.get(m)
            if cur is None or (total, keys[(x, y, r)]) < (cur.frames, cur.keys):
                best[m] = Operation(m, keys[(x, y, r)], total)
        return {m: best[m] for m in ALL_MOVES if m in best}


def _top(field) -> list[bool]:
    return [t != 0 for t in field.top]


def plan_operations(field) -> dict[Move, Operation]:
    """置ける場所ごとの最短の操作。C++ 版があればそれを使う（結果は同じ）。"""
    h, top = field.heights(), _top(field)
    try:
        from . import _puyocpp
    except ImportError:
        return Controller(h, top).plan()
    return {Move(x, r): Operation(Move(x, r), keys, frames) for x, r, keys, frames in _puyocpp.plan_operations(h, top)}


def operation_path(field, op: Operation) -> list[tuple[int, int, int]]:
    """操作の途中の組ぷよの状態（軸の x, y と向き r）。"""
    return Controller(field.heights(), _top(field)).path(op.keys)


def reachable_moves(field) -> set[Move]:
    h = field.heights()
    if max(h) <= 11:  # 12 段以上の列が無ければどこでも置ける
        return set(ALL_MOVES)
    return set(Controller(h, _top(field)).plan())
