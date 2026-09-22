"""対戦（2 人）のゲーム進行。

ルール:
  - 2 人とも同じツモ列を使う（ぷよぷよ通と同じ）
  - 時間はフレーム単位で進む。1 手 hand_frames（ちぎりは +tear_frames）、連鎖 1 段 chain_frames、
    おじゃまの落下 ojama_frames。既定値は書籍の「N 連鎖の間に約 1.5N 手置ける」に合わせている
  - 連鎖の各段の得点を ojama_rate 点で 1 個のおじゃまに換算（端数は次の連鎖に持ち越し）。
    自分に来る予定のおじゃまがあれば先に相殺し、残りを相手に送る
  - おじゃまは、相手の連鎖がすべて終わった後に置いた 1 手の後に降る（自分がその手で連鎖したら連鎖の後）。
    1 回に最大 max_ojama_rows 段（6 段 = 36 個）。残りは次の手の後に降る
  - 3 列目の 12 段目が埋まったら負け。どちらかが max_hands 手に達したら引き分け
"""

from __future__ import annotations

import math
import random
import time
import traceback
from dataclasses import dataclass
from dataclasses import field as dc_field

from .ai import AI, load_ai_class
from .core import WIDTH, Field
from .game import GameState
from .tsumo import TsumoGenerator


@dataclass(frozen=True)
class VersusRules:
    hand_frames: int = 40
    tear_frames: int = 20
    chain_frames: int = 60
    ojama_frames: int = 30
    ojama_rate: int = 70
    max_ojama_rows: int = 6
    max_hands: int = 250
    visible_nexts: int = 2
    tsumo_mode: str = "ac"


@dataclass(frozen=True)
class VersusInfo:
    """AI に渡す対戦の情報（GameState.versus）。"""

    now: int  # 今の時刻（フレーム）
    incoming: int  # 自分に来ることが確定しているおじゃま（相殺後）
    incoming_total: int  # 相手が連鎖中なら、その残りの段で来る分も含めた見込み
    window: int  # おじゃまが降るまでに置ける手数（この手を含む）。来ないなら 0
    carry: int  # 自分の得点の端数（おじゃまに換算していない分）
    opp_field: Field
    opp_incoming: int
    opp_chaining: bool
    opp_chain_end: int
    opp_hand: int
    opp_pairs: tuple  # 相手がこれから置く組ぷよのうち、自分に見えている範囲（共通のツモ列）
    rules: VersusRules


@dataclass
class PlayerStats:
    max_chain: int = 0
    max_score: int = 0
    sent: int = 0  # 相手に送った（相殺で消えた分も含む）おじゃま
    received: int = 0  # 実際に降ってきたおじゃま
    fires: int = 0


@dataclass
class _Player:
    idx: int
    ai: AI
    field: Field = dc_field(default_factory=Field)
    hand: int = 0
    t_next: int = 0
    phase: str = "decide"  # decide → settle → decide ...
    place_start: int = 0
    chain_end: int = 0
    carry: int = 0
    incoming: int = 0
    emissions: list[tuple[int, int]] = dc_field(default_factory=list)  # (時刻, 個数)
    dead: bool = False
    think_ms: float = 0.0
    stats: PlayerStats = dc_field(default_factory=PlayerStats)
    snapshots: list[dict] = dc_field(default_factory=list)


@dataclass
class VersusResult:
    seed: int
    winner: int | None  # 0 / 1 / None（引き分け）
    reason: str
    time: int
    hands: tuple[int, int]
    stats: tuple[PlayerStats, PlayerStats]
    think_ms: tuple[float, float]
    error: str | None = None
    replay: dict | None = None
    events: list[tuple] = dc_field(default_factory=list)  # (時刻, 手番, "fire"/"drop", ...)


class VersusGame:
    def __init__(self, ais: tuple[AI, AI], seed: int, rules: VersusRules = VersusRules(), record: bool = False):
        self.rules = rules
        self.seed = seed
        self.tsumo = TsumoGenerator(seed, rules.tsumo_mode)
        self.rng = random.Random(seed * 7919 + 1)  # おじゃまの端数の落ちる列
        self.players = [_Player(0, ais[0]), _Player(1, ais[1])]
        self.record = record
        self.now = 0
        self.incoming_log: list[tuple[int, int, int]] = []
        self.events: list[tuple] = []

    # ------------------------------------------------------------------

    def run(self) -> VersusResult:
        error = None
        while True:
            p = min(self.players, key=lambda q: (q.t_next, 0 if q.phase == "settle" else 1, q.idx))
            self.now = p.t_next
            self._emit_until(self.now)
            if p.phase == "decide":
                if p.hand >= self.rules.max_hands:
                    return self._result(None, "max_hands")
                try:
                    self._decide(p)
                except Exception:
                    error = traceback.format_exc(limit=3)
                    return self._result(1 - p.idx, "error", error)
            else:
                self._settle(p)
                if p.dead:
                    return self._result(1 - p.idx, "dead")

    def _other(self, p: _Player) -> _Player:
        return self.players[1 - p.idx]

    def _emit_until(self, t: int) -> None:
        """時刻 t までに発生したおじゃまを、相殺してから相手に送る。"""
        events = sorted(
            (et, q.idx, amount) for q in self.players for et, amount in q.emissions if et <= t
        )
        if not events:
            return
        for q in self.players:
            q.emissions = [(et, a) for et, a in q.emissions if et > t]
        for et, idx, amount in events:
            q, opp = self.players[idx], self.players[1 - idx]
            cancel = min(amount, q.incoming)
            q.incoming -= cancel
            opp.incoming += amount - cancel
            q.stats.sent += amount
            self._log_incoming(et)

    def _log_incoming(self, t: int) -> None:
        if self.record:
            self.incoming_log.append((t, self.players[0].incoming, self.players[1].incoming))

    def info(self, p: _Player) -> VersusInfo:
        opp = self._other(p)
        future = sum(a for _, a in opp.emissions)
        total = p.incoming + future
        if total == 0:
            window = 0
        elif opp.chain_end <= self.now:
            window = 1
        else:
            window = math.ceil((opp.chain_end - self.now) / self.rules.hand_frames) + 1
        return VersusInfo(
            now=self.now,
            incoming=p.incoming,
            incoming_total=total,
            window=window,
            carry=p.carry,
            opp_field=opp.field.copy(),
            opp_incoming=opp.incoming,
            opp_chaining=opp.chain_end > self.now,
            opp_chain_end=opp.chain_end,
            opp_hand=opp.hand,
            opp_pairs=tuple(self.tsumo.get(h) for h in range(opp.hand, p.hand + 1 + self.rules.visible_nexts)),
            rules=self.rules,
        )

    def _decide(self, p: _Player) -> None:
        r = self.rules
        pair = self.tsumo.get(p.hand)
        state = GameState(
            field=p.field.copy(),
            current=pair,
            nexts=tuple(self.tsumo.get(p.hand + i + 1) for i in range(r.visible_nexts)),
            hand=p.hand,
            score=0,
            versus=self.info(p),
        )
        info = state.versus
        t0 = time.perf_counter()
        move = p.ai.decide(state)
        p.think_ms += (time.perf_counter() - t0) * 1000
        if not p.field.is_reachable(move):
            raise ValueError(f"player {p.idx} hand {p.hand}: move {move} is not reachable")

        placed = p.field.copy()
        tear = placed.place(pair, move)
        after = placed.copy()
        chain = after.resolve_chain()
        t_placed = self.now + r.hand_frames + (r.tear_frames if tear else 0)
        self._snap(p, self.now, placed, label=f"{pair} {move}", move=(move.x, move.rot))
        p.hand += 1

        if chain.chains:
            total = p.carry
            f = placed.copy()
            for k, step in enumerate(chain.steps):
                before = total // r.ojama_rate
                total += step.score
                t_step = t_placed + (k + 1) * r.chain_frames
                p.emissions.append((t_step, total // r.ojama_rate - before))
                if self.record:
                    self._snap(p, t_placed + k * r.chain_frames, f, erase=step.erased, label=f"{k + 1}連鎖")
                    f._remove(step.erased)
                    self._snap(p, t_placed + k * r.chain_frames + r.chain_frames // 2, f, label=f"{k + 1}連鎖")
            p.carry = total % r.ojama_rate
            self.events.append((self.now, p.idx, "fire", chain.chains, sum(a for _, a in p.emissions),
                                info.incoming_total, info.window, p.hand))
            p.chain_end = t_placed + chain.chains * r.chain_frames
            p.t_next = p.chain_end
            p.stats.fires += 1
            if (chain.chains, chain.score) > (p.stats.max_chain, p.stats.max_score):
                p.stats.max_chain, p.stats.max_score = chain.chains, chain.score
        else:
            p.t_next = t_placed
        p.field = after
        p.place_start = self.now
        p.phase = "settle"

    def _settle(self, p: _Player) -> None:
        r = self.rules
        opp = self._other(p)
        t = self.now
        # 相手の連鎖が終わった後に置いた手なら、おじゃまが降る
        if p.incoming > 0 and p.place_start >= opp.chain_end:
            n = min(p.incoming, r.max_ojama_rows * WIDTH)
            p.field.drop_ojama(n, self.rng)
            p.incoming -= n
            p.stats.received += n
            self.events.append((self.now, p.idx, "drop", n, p.incoming, p.hand))
            t += r.ojama_frames
            self._log_incoming(self.now)
            self._snap(p, self.now, p.field, label=f"おじゃま {n}")
        p.dead = p.field.is_dead()
        p.phase = "decide"
        p.t_next = t

    def _snap(self, p: _Player, t: int, f: Field, erase=(), label: str = "", move=None) -> None:
        if not self.record:
            return
        nexts = [str(self.tsumo.get(p.hand + i)) for i in range(1 + self.rules.visible_nexts)]
        p.snapshots.append(
            {"t": t, "field": f.to_json(), "erase": list(erase), "label": label, "hand": p.hand, "pairs": nexts,
             "move": move}
        )

    def _result(self, winner: int | None, reason: str, error: str | None = None) -> VersusResult:
        a, b = self.players
        replay = None
        if self.record:
            replay = {
                "seed": self.seed,
                "winner": winner,
                "reason": reason,
                "rules": self.rules.__dict__,
                "players": [
                    {"ai": getattr(q.ai, "label", q.ai.name), "snapshots": q.snapshots, "stats": q.stats.__dict__}
                    for q in self.players
                ],
                "incoming": self.incoming_log,
                "end": self.now,
            }
        return VersusResult(
            seed=self.seed,
            winner=winner,
            reason=reason,
            time=self.now,
            hands=(a.hand, b.hand),
            stats=(a.stats, b.stats),
            think_ms=(a.think_ms, b.think_ms),
            error=error,
            replay=replay,
            events=self.events,
        )


# ----------------------------------------------------------------------
# 対戦の実行
# ----------------------------------------------------------------------


@dataclass
class MatchConfig:
    ai1: str
    ai2: str
    opts1: dict = dc_field(default_factory=dict)
    opts2: dict = dc_field(default_factory=dict)
    games: int = 100
    seed: int = 0
    rules: VersusRules = VersusRules()


def play_match(cfg: MatchConfig, seed: int, record: bool = False) -> VersusResult:
    """seed が奇数なら左右を入れ替える（同時刻の処理順の有利不利を打ち消すため）。結果は ai1 から見た向きに直す。"""
    swap = seed % 2 == 1
    specs = [(cfg.ai1, cfg.opts1, "ai1"), (cfg.ai2, cfg.opts2, "ai2")]
    if swap:
        specs.reverse()
    ais = []
    for i, (name, opts, label) in enumerate(specs):
        ai = load_ai_class(name)(seed=seed * 2 + i, **opts)
        ai.label = f"{name}（{label}）"
        ais.append(ai)
    res = VersusGame((ais[0], ais[1]), seed, cfg.rules, record=record).run()
    if swap:
        res.winner = None if res.winner is None else 1 - res.winner
        res.hands = res.hands[::-1]
        res.stats = res.stats[::-1]
        res.think_ms = res.think_ms[::-1]
        res.events = [(e[0], 1 - e[1], *e[2:]) for e in res.events]
    return res


def _play_one(args) -> VersusResult:
    cfg, seed = args
    return play_match(cfg, seed)


def run_matches(cfg: MatchConfig, jobs: int = 1) -> list[VersusResult]:
    from concurrent.futures import ProcessPoolExecutor

    tasks = [(cfg, cfg.seed + i) for i in range(cfg.games)]
    if jobs <= 1:
        return [_play_one(t) for t in tasks]
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        return list(ex.map(_play_one, tasks))


def format_matches(cfg: MatchConfig, rs: list[VersusResult]) -> str:
    n = len(rs)
    w = [r.winner for r in rs]
    win, lose, draw = w.count(0), w.count(1), w.count(None)
    # 勝率の 95% 信頼区間（正規近似、引き分けは 0.5 勝）
    p = (win + 0.5 * draw) / n
    ci = 1.96 * math.sqrt(max(p * (1 - p), 1e-9) / n)
    moves = [sum(r.hands) for r in rs]

    def avg(f):
        return sum(f(r) for r in rs) / n

    def side(i):
        return (
            f"最大連鎖 平均 {avg(lambda r: r.stats[i].max_chain):5.2f}  "
            f"送ったおじゃま 平均 {avg(lambda r: r.stats[i].sent):6.1f}  "
            f"受けたおじゃま 平均 {avg(lambda r: r.stats[i].received):5.1f}  "
            f"発火回数 平均 {avg(lambda r: r.stats[i].fires):4.1f}  "
            f"思考 {sum(r.think_ms[i] for r in rs) / max(1, sum(r.hands[i] for r in rs)):.1f} ms/手"
        )

    lines = [
        f"{cfg.ai1} {cfg.opts1 or ''} vs {cfg.ai2} {cfg.opts2 or ''}  （{n} 局、奇数シードは左右入れ替え）",
        f"  勝ち {win} / 負け {lose} / 引き分け {draw}   勝率 {p * 100:.1f}% ± {ci * 100:.1f}%",
        f"  平均手数（2 人の合計）{sum(moves) / n:.1f}   平均時間 {avg(lambda r: r.time) / 60:.1f} 秒",
        f"  ai1: {side(0)}",
        f"  ai2: {side(1)}",
    ]
    errors = [r for r in rs if r.error]
    if errors:
        lines.append(f"  !! エラー {len(errors)} 局（最初: seed={errors[0].seed}）\n{errors[0].error}")
    return "\n".join(lines)


def record_match(args) -> dict:
    """1 局を記録してリプレイ HTML を書き出し、一覧ページ用の要約を返す（並列実行用）。"""
    from pathlib import Path

    from .replay import write_versus_replay

    cfg, seed, out = args
    r = play_match(cfg, seed, record=True)
    write_versus_replay(r.replay, out)
    return {"file": Path(out).name, "seed": seed, "winner": r.winner, "reason": r.reason, "hands": r.hands,
            "stats": [s.__dict__ for s in r.stats], "events": r.events}
