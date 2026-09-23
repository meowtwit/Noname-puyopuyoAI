"""盤面評価ネットワークの教師データを作る。

    python scripts/gen_nn_data.py -n 3000 -o results/nn_data.npz

beam AI にとこぷよを打たせ、1 手ごとの盤面（置いて連鎖した後）と、その手で撃った連鎖数・撃った時点のぷよ数・
窒息したかを記録する。ラベル（その盤面の良さ）は学習時に scripts/train_nn.py で計算する。
  - 良い形も悪い形も集めるため、ゲームごとに評価の重み・探索の広さを変え、一定の確率でランダムな手を打たせる
盤面は int8 の (6, 14) 配列（色コード: 0=空, 1=R, 2=G, 3=B, 4=Y, 5=O）。
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from puyo.ai.sampling_cpp import BeamCppAI  # noqa: E402
from puyo.core import HEIGHT, TOP_ROW, WIDTH, simulate  # noqa: E402
from puyo.game import Tokopuyo  # noqa: E402


def encode(field) -> np.ndarray:
    a = np.zeros((WIDTH, TOP_ROW), dtype=np.int8)
    for x in range(WIDTH):
        col = field.cols[x]
        a[x, : len(col)] = [int(c) for c in col]
        a[x, HEIGHT] = int(field.top[x])
    return a


def play(args) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, bool]:
    seed, max_hands = args
    rng = random.Random(seed * 7 + 3)
    opts = {
        "width": rng.choice([12, 16, 20]),
        "samples": rng.choice([2, 3, 4]),
        "depth": rng.choice([6, 8]),
        "fire": 14,
        "w_shape": rng.uniform(3, 20),
        "conn2": rng.uniform(0, 40),
        "conn3": rng.uniform(0, 100),
        "w_need": rng.uniform(100, 500),
    }
    eps = rng.choice([0.0, 0.0, 0.05, 0.15])  # ランダムな手を打つ確率
    ai = BeamCppAI(seed=seed, **opts)
    g = Tokopuyo(seed=seed, max_hands=max_hands)
    fields, fired, fire_puyos = [], [], []
    while g.hand < max_hands and not g.dead:
        st = g.state()
        move = ai.decide(st)
        if rng.random() < eps:
            safe = [m for m in st.legal_moves() if not simulate(st.field, st.current, m)[0].is_dead()]
            move = rng.choice(safe or st.legal_moves())
        res = g.step(move)
        fields.append(encode(g.field))
        fired.append(res.chain.chains)
        fire_puyos.append(res.placed.count() if res.chain.chains else 0)
        if res.chain.chains >= 14:
            break
    x = np.stack(fields) if fields else np.zeros((0, WIDTH, TOP_ROW), np.int8)
    return x, np.array(fired, np.int8), np.array(fire_puyos, np.int8), np.arange(len(fields), dtype=np.int16), g.dead


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--games", type=int, default=3000)
    ap.add_argument("--hands", type=int, default=60)
    ap.add_argument("--seed", type=int, default=500_000)
    ap.add_argument("-j", "--jobs", type=int, default=8)
    ap.add_argument("-o", "--out", default="results/nn_data.npz")
    a = ap.parse_args()
    t0 = time.time()
    X, F, P, G, H, D = [], [], [], [], [], []
    with ProcessPoolExecutor(a.jobs) as ex:
        tasks = [(a.seed + i, a.hands) for i in range(a.games)]
        for gi, (x, fired, fp, h, dead) in enumerate(ex.map(play, tasks, chunksize=4)):
            X.append(x)
            F.append(fired)
            P.append(fp)
            H.append(h)
            G.append(np.full(len(h), gi, dtype=np.int32))
            D.append(np.full(len(h), dead, dtype=bool))
            if (gi + 1) % 500 == 0:
                print(f"  {gi + 1}/{a.games} ゲーム（{time.time() - t0:.0f}s）", flush=True)
    cat = np.concatenate
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(a.out, X=cat(X), fired=cat(F), fire_puyos=cat(P), game=cat(G), hand=cat(H), dead=cat(D))
    print(f"{sum(len(h) for h in H)} 盤面を保存: {a.out}  窒息 {sum(d[0] for d in D if len(d))} ゲーム"
          f"  （{time.time() - t0:.0f}s）")


if __name__ == "__main__":
    main()
