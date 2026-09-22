"""AI の登録と読み込み。

組み込み AI は名前で、自作 AI は "パッケージ.モジュール:クラス名" で指定できる。
"""

from __future__ import annotations

import importlib

from .base import AI

BUILTIN = {
    "random": "puyo.ai.random_ai:RandomAI",
    "greedy": "puyo.ai.greedy:GreedyAI",
    "lookahead": "puyo.ai.lookahead:LookaheadAI",
}


def load_ai_class(spec: str) -> type[AI]:
    path = BUILTIN.get(spec, spec)
    if ":" not in path:
        raise ValueError(f"unknown AI {spec!r}. builtin: {sorted(BUILTIN)} or 'module:Class'")
    module, cls = path.split(":", 1)
    return getattr(importlib.import_module(module), cls)


__all__ = ["AI", "BUILTIN", "load_ai_class"]
