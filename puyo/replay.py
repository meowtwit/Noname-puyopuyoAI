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


def write_versus_index(entries: list[dict], names: tuple[str, str], title: str, path: str | Path) -> Path:
    """対戦リプレイの一覧ページ。entries: {file, seed, winner, reason, hands, stats, events}"""
    import html as _html

    path = Path(path)
    wins = sum(e["winner"] == 0 for e in entries)
    loses = sum(e["winner"] == 1 for e in entries)
    rows = []
    for e in entries:
        w = "引き分け" if e["winner"] is None else names[e["winner"]]
        cls = "" if e["winner"] is None else ("w" if e["winner"] == 0 else "l")
        fires = " → ".join(
            f"{'①' if ev[1] == 0 else '②'}{ev[3]}連鎖({ev[4]})" for ev in e["events"] if ev[2] == "fire"
        )
        s0, s1 = e["stats"]
        rows.append(
            f"<tr class='{cls}'><td><a href='{_html.escape(e['file'])}'>seed {e['seed']}</a></td><td>{_html.escape(w)}</td>"
            f"<td>{e['reason']}</td><td>{e['hands'][0]} / {e['hands'][1]}</td>"
            f"<td>{s0['max_chain']} / {s1['max_chain']}</td><td class='f'>{_html.escape(fires)}</td></tr>"
        )
    page = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>対戦リプレイ一覧</title>
<style>
:root {{ --bg:#14161c; --panel:#1e2129; --text:#e7e9ee; --muted:#8a90a0; --line:#2d313c; --win:#3fbf5a; --lose:#e8464b; }}
body {{ margin:0; background:var(--bg); color:var(--text); font:14px/1.5 system-ui,-apple-system,"Hiragino Sans",sans-serif; }}
main {{ max-width:1100px; margin:0 auto; padding:16px; }}
h1 {{ font-size:16px; margin:0 0 4px; }} .sub {{ color:var(--muted); font-size:12px; margin-bottom:12px; }}
table {{ width:100%; border-collapse:collapse; }} th, td {{ padding:6px 8px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
th {{ color:var(--muted); font-weight:500; font-size:12px; }} a {{ color:#7fb0ff; }}
tr.w td:nth-child(2) {{ color:var(--win); }} tr.l td:nth-child(2) {{ color:var(--lose); }}
td.f {{ font-size:12px; color:var(--muted); }}
@media (max-width:700px) {{ td.f {{ display:none; }} }}
</style></head><body><main>
<h1>{_html.escape(title)}</h1>
<div class="sub">① {_html.escape(names[0])} ／ ② {_html.escape(names[1])} ・ {len(entries)} 局：①の {wins} 勝 {loses} 敗 {len(entries) - wins - loses} 分。
発火の列は「誰が 何連鎖(送ったおじゃま)」の順。</div>
<table><tr><th>リプレイ</th><th>勝者</th><th>理由</th><th>手数 ①/②</th><th>最大連鎖 ①/②</th><th>発火の流れ</th></tr>
{"".join(rows)}</table></main></body></html>"""
    path.write_text(page)
    return path


def write_replays_home(root: str | Path = "replays") -> Path:
    """replays/ 以下のリプレイ一覧（各ディレクトリの index.html）をまとめたトップページ。"""
    import html as _html
    import re

    root = Path(root)
    items = []
    for idx in sorted(root.glob("*/index.html"), key=lambda p: p.stat().st_mtime, reverse=True):
        text = idx.read_text()
        m = re.search(r'<div class="sub">(.*?)</div>', text, re.S)
        sub = re.sub(r"<[^>]+>", "", m.group(1)).split("発火の列")[0].strip() if m else ""
        items.append(f"<li><a href='{_html.escape(idx.parent.name)}/index.html'>{_html.escape(idx.parent.name)}</a>"
                     f"<div>{_html.escape(sub)}</div></li>")
    page = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>リプレイ置き場</title>
<style>
:root {{ --bg:#14161c; --text:#e7e9ee; --muted:#8a90a0; --line:#2d313c; }}
body {{ margin:0; background:var(--bg); color:var(--text); font:14px/1.5 system-ui,-apple-system,"Hiragino Sans",sans-serif; }}
main {{ max-width:900px; margin:0 auto; padding:16px; }} h1 {{ font-size:16px; }}
ul {{ list-style:none; padding:0; }} li {{ padding:10px 0; border-bottom:1px solid var(--line); }}
li div {{ color:var(--muted); font-size:12px; }} a {{ color:#7fb0ff; font-weight:600; }}
</style></head><body><main><h1>リプレイ置き場（新しい順）</h1><ul>{"".join(items)}</ul></main></body></html>"""
    out = root / "index.html"
    out.write_text(page)
    return out
