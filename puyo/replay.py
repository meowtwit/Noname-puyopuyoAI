"""対局ログを JSON / 単体で開ける HTML ビューアに書き出す。"""

from __future__ import annotations

import json
from pathlib import Path

from .game import Tokopuyo

VIEWER_TEMPLATE = Path(__file__).with_name("viewer.html")


def build_replay(game: Tokopuyo, ai_name: str) -> dict:
    """1 手ごとに「設置 → (消去 → 落下) × 連鎖数」のフレーム列を作る。"""
    steps = []
    for st in game.history:
        frames = [{"field": st.placed.to_json(), "erase": [], "label": "設置"}]
        f = st.placed.copy()
        for cs in st.chain.steps:
            frames.append({"field": f.to_json(), "erase": cs.erased, "label": f"{cs.chain}連鎖"})
            f._remove(cs.erased)
            frames.append({"field": f.to_json(), "erase": [], "label": f"{cs.chain}連鎖"})
        steps.append(
            {
                "hand": st.hand,
                "pair": str(st.pair),
                "move": {"x": st.move.x, "rot": st.move.rot, "str": str(st.move)},
                "nexts": [str(game.tsumo.get(st.hand + i + 1)) for i in range(game.visible_nexts)],
                "chain": st.chain.chains,
                "score": st.chain.score,
                "tear": st.tear,
                "dead": st.dead,
                "think_ms": round(st.think_ms, 2),
                "frames": frames,
            }
        )
    return {
        "seed": game.seed,
        "ai": ai_name,
        "tsumo_mode": game.tsumo_mode,
        "total_score": game.score,
        "max_chain": max((s["chain"] for s in steps), default=0),
        "steps": steps,
    }


def write_replay(replay: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".json":
        path.write_text(json.dumps(replay, ensure_ascii=False))
    else:
        html = VIEWER_TEMPLATE.read_text().replace("/*__REPLAY_DATA__*/null", json.dumps(replay, ensure_ascii=False))
        path.write_text(html)
    return path


VERSUS_VIEWER_TEMPLATE = Path(__file__).with_name("versus_viewer.html")


def write_versus_replay(replay: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".json":
        path.write_text(json.dumps(replay, ensure_ascii=False))
    else:
        html = VERSUS_VIEWER_TEMPLATE.read_text().replace("/*__REPLAY_DATA__*/null", json.dumps(replay, ensure_ascii=False))
        path.write_text(html)
    return path
