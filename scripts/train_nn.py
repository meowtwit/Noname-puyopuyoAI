"""盤面評価ネットワーク（この盤面から何連鎖撃てそうか）を学習し、C++ で使う形式で書き出す。

    python scripts/train_nn.py results/nn_data.npz -o models/eval_mlp.bin

入力: 各マス（6 列 × 14 段）× 色（R, G, B, Y, おじゃま）の 0/1 = 420 個
出力: その盤面から先で撃つ連鎖の「質」の予測（--label）:
  quality（既定）: その後に撃った最大の連鎖について 連鎖数 − (撃った時点のぷよ数 − 連鎖数 × 4) / 4
                  = 4 個ずつ無駄なく伸ばした長い連鎖ほど大きい。窒息・撃たずに終わったら 0
  chains        : その後に撃った最大の連鎖数（盤面が埋まるほど大きくなり「積むほど良い」と覚えてしまう）
学習時は 4 色をランダムに入れ替えて増やす（色の違いに意味は無いため）。検証はゲーム単位で分ける。

書き出す形式（little endian）: "PNN1", int32 層数, 各層 { int32 入力数, int32 出力数, float32 重み[入力][出力], float32 バイアス[出力] }
1 層目は入力の大半が 0 なので、C++ では置かれているマスの重みの行を足すだけで計算する。
"""

from __future__ import annotations

import argparse
import struct
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

WIDTH, ROWS, COLORS = 6, 14, 5
N_IN = WIDTH * ROWS * COLORS


def one_hot(X: np.ndarray) -> torch.Tensor:
    """(N, 6, 14) の色コード → (N, 420)。"""
    x = torch.from_numpy(X.astype(np.int64))
    oh = torch.nn.functional.one_hot(x, 6)[..., 1:]  # 空（0）を除く
    return oh.reshape(len(X), -1).float()


def permute_colors(x: torch.Tensor) -> torch.Tensor:
    """4 色（R, G, B, Y）を盤面ごとにランダムに入れ替える。"""
    n = x.shape[0]
    v = x.view(n, WIDTH * ROWS, COLORS)
    perm = torch.argsort(torch.rand(n, 4), dim=1)
    idx = torch.cat([perm, torch.full((n, 1), 4)], dim=1)  # おじゃまはそのまま
    return torch.gather(v, 2, idx.unsqueeze(1).expand(-1, WIDTH * ROWS, -1)).reshape(n, -1)


def make_labels(d, mode: str) -> np.ndarray:
    """ゲームごとに、各盤面より後に撃った最大の連鎖から良さを計算する。"""
    fired, puyos, game = d["fired"].astype(np.int32), d["fire_puyos"].astype(np.int32), d["game"]
    y = np.zeros(len(fired), dtype=np.float32)
    best = 0.0
    for i in range(len(fired) - 1, -1, -1):
        if i == len(fired) - 1 or game[i + 1] != game[i]:
            best = 0.0  # 次のゲーム（窒息・撃たずに終わったら 0 から）
        y[i] = best
        c = fired[i]
        if c:
            v = c if mode == "chains" else c - (puyos[i] - 4 * c) / 4
            best = max(best, v)
    return y


def make_model(h1: int, h2: int) -> nn.Module:
    return nn.Sequential(nn.Linear(N_IN, h1), nn.ReLU(), nn.Linear(h1, h2), nn.ReLU(), nn.Linear(h2, 1))


def export(model: nn.Module, path: Path) -> None:
    layers = [m for m in model if isinstance(m, nn.Linear)]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"PNN1")
        f.write(struct.pack("<i", len(layers)))
        for l in layers:
            w = l.weight.detach().cpu().numpy().T.astype("<f4")  # [入力][出力]
            f.write(struct.pack("<ii", w.shape[0], w.shape[1]))
            f.write(w.tobytes())
            f.write(l.bias.detach().cpu().numpy().astype("<f4").tobytes())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("-o", "--out", default="models/eval_mlp.bin")
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--h1", type=int, default=64)
    ap.add_argument("--h2", type=int, default=32)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--batch", type=int, default=1024)
    ap.add_argument("--label", default="quality", choices=["quality", "chains"])
    a = ap.parse_args()
    torch.manual_seed(0)

    d = np.load(a.data)
    X, game = d["X"], d["game"]
    y = make_labels(d, a.label)
    val_games = set(np.unique(game)[::10])  # 1 割のゲームを検証用に
    is_val = np.isin(game, list(val_games))
    xtr, ytr = one_hot(X[~is_val]), torch.from_numpy(y[~is_val])
    xva, yva = one_hot(X[is_val]), torch.from_numpy(y[is_val])
    print(f"学習 {len(ytr)} 盤面 / 検証 {len(yva)} 盤面（{len(val_games)} ゲーム）  ラベル平均 {y.mean():.2f}")

    model = make_model(a.h1, a.h2)
    opt = torch.optim.Adam(model.parameters(), lr=a.lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, a.epochs)
    base = float(((yva - ytr.mean()) ** 2).mean())
    for ep in range(a.epochs):
        t0 = time.time()
        model.train()
        order = torch.randperm(len(ytr))
        total = 0.0
        for i in range(0, len(order), a.batch):
            b = order[i : i + a.batch]
            pred = model(permute_colors(xtr[b])).squeeze(1)
            loss = ((pred - ytr[b]) ** 2).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += float(loss) * len(b)
        sched.step()
        model.eval()
        with torch.no_grad():
            pv = model(xva).squeeze(1)
            mse = float(((pv - yva) ** 2).mean())
            r = float(np.corrcoef(pv.numpy(), yva.numpy())[0, 1])
        print(f"  epoch {ep + 1:2d}: 学習 MSE {total / len(ytr):6.2f}  検証 MSE {mse:6.2f}"
              f"（平均で予測すると {base:.2f}）  相関 {r:.3f}  {time.time() - t0:.0f}s", flush=True)

    export(model, Path(a.out))
    print(f"書き出し: {a.out}")


if __name__ == "__main__":
    main()
