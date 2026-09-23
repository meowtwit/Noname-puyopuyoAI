"""見えないツモを推測する C++ AI（beam_cpp / mcts_cpp）の呼び出し。

ツモの推測モデル（--opt tsumo_model=...）:
  ac      : AC 通と同じく 128 手で各色 64 個。これまでに見た色を数え、今の周期の残りから引く（既定）
  uniform : 各色 1/4 の独立な抽選

ビルド: python scripts/build_cpp.py
"""

from __future__ import annotations

from ..core import Move, Pair
from ..game import GameState
from .base import AI

try:
    from .. import _puyocpp
except ImportError as e:  # pragma: no cover
    raise ImportError("C++ モジュールが未ビルドです。`python scripts/build_cpp.py` を実行してください") from e

CYCLE_HANDS = 128
PER_COLOR = 64


class SamplingCppAI(AI):
    impl_class = None

    def __init__(self, seed: int = 0, **options):
        super().__init__(seed, **options)
        opts = dict(options)
        self.tsumo_model = opts.pop("tsumo_model", "ac")
        nn_path = opts.pop("nn", None)  # 盤面評価ネットワーク（scripts/train_nn.py）。w_nn と一緒に使う
        if nn_path and not _puyocpp.load_nn(str(nn_path)):
            raise ValueError(f"ネットワークを読み込めません: {nn_path}")
        if self.tsumo_model not in ("ac", "uniform"):
            raise ValueError(f"unknown tsumo_model: {self.tsumo_model}")
        self.impl = self.impl_class({k: float(v) for k, v in opts.items()}, seed)
        self.seen: dict[int, Pair] = {}  # 手数 → 見た組ぷよ

    def remaining(self, state: GameState) -> list[int] | None:
        """今の周期で、見えているツモまでを除いて残っている R, G, B, Y の個数。"""
        if self.tsumo_model != "ac":
            return None
        visible = [state.current, *state.nexts]
        for i, p in enumerate(visible):
            self.seen[state.hand + i] = p
        start = state.hand // CYCLE_HANDS * CYCLE_HANDS
        last = min(state.hand + len(visible) - 1, start + CYCLE_HANDS - 1)
        counts = [PER_COLOR] * 4
        for h in range(start, last + 1):
            p = self.seen.get(h)
            if p is not None:
                counts[p.axis - 1] -= 1
                counts[p.child - 1] -= 1
        return [max(0, c) for c in counts]

    def decide(self, state: GameState) -> Move:
        pairs = [str(state.current), *(str(p) for p in state.nexts)]
        hands_left = -1 if state.hands_left is None else state.hands_left
        x, rot = self.impl.decide(state.field.to_json(), pairs, hands_left, self.remaining(state))
        return Move(x, rot)


class BeamCppAI(SamplingCppAI):
    """見えないツモの期待値を取るビームサーチ（オプション: width, depth, samples, fire, 評価関数の重み）。"""

    name = "beam_cpp"
    impl_class = _puyocpp.BeamAI


class MctsCppAI(SamplingCppAI):
    """見えないツモを推測し直す open-loop MCTS（オプション: iterations, depth, c, fire, 評価関数の重み）。"""

    name = "mcts_cpp"
    impl_class = _puyocpp.MctsAI


class VersusCppAI(SamplingCppAI):
    """対戦用（相手の発火中に打ち返す）。オプション: accept, w_ojama, counter_need, kill_margin ＋ beam のオプション。

    とこぷよ（state.versus が無い）ではおじゃまが来ないので、beam_cpp とほぼ同じ動きになる。
    """

    name = "versus_cpp"
    impl_class = _puyocpp.VersusAI

    def decide(self, state: GameState) -> Move:
        pairs = [str(state.current), *(str(p) for p in state.nexts)]
        v = state.versus
        if v is None:
            x, rot = self.impl.decide(state.field.to_json(), pairs, self.remaining(state), 0, 0, 0, [""] * 6)
        else:
            x, rot = self.impl.decide(
                state.field.to_json(), pairs, self.remaining(state), v.incoming_total, v.window, v.carry,
                v.opp_field.to_json(), [str(p) for p in v.opp_pairs], v.rules.hand_frames, v.rules.chain_frames,
                state.hand,
            )
        return Move(x, rot)
