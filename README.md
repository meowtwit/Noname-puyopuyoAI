# PuyopuyoAI

ぷよぷよ（通ルール）で **とこぷよ 10 連鎖** を安定して打てる AI を作るための試験環境。
ルールと評価方法は「第１回ぷよぷよ人類vsAI」（puyoai / mayah）を参考にしている。

## セットアップ

```sh
python3 -m venv .venv
.venv/bin/pip install pytest
.venv/bin/python -m pytest        # ルール実装のテスト
```

外部ライブラリは不要（Python 3.11+）。

## 使い方

```sh
# AI を 200 ゲーム評価（8 並列）
.venv/bin/python -m puyo bench --ai greedy -n 200 -j 8

# 1 ゲーム実行してリプレイ HTML を出力し、ブラウザで開く
.venv/bin/python -m puyo play --ai greedy --seed 3 --no-stop --open

# 盤面に 1 手置いて連鎖を確認（書籍の階段 5 連鎖）
.venv/bin/python -m puyo sim 'ORBYG./RBYGR./RBYGR./RBYGR.' --pair RR --move 6^
```

主なオプション（bench / play 共通）:

| オプション | 既定 | 意味 |
|---|---|---|
| `--ai` | greedy | `random` / `greedy` / `lookahead` / `モジュール:クラス` |
| `--hands` | 50 | 最大手数 |
| `--target` | 10 | 目標連鎖数（発火したらそのゲームは終了） |
| `--no-stop` | – | 目標を達成しても最大手数まで続ける |
| `--mode` | ac | ツモ方式 `ac` / `classic16` / `random` |
| `--nexts` | 2 | AI に見せる NEXT 数（アーケード実機に近づけるなら 1） |
| `--opt K=V` | – | AI にパラメータを渡す（パラメータ調整用） |
| `-o` | – | bench: 結果 JSON、play: リプレイの出力先 |

## 評価指標（bench の出力）

書籍 4.5「評価関数の評価」に準拠: 各ゲームは **窒息 / 最大手数 / 目標連鎖の発火** で終了し、発火した最大連鎖を記録する。

- **10連鎖以上 発火率** … 最終目標の指標
- **最大連鎖 中央値** … 書籍と同じく平均ではなく中央値で比較
- 窒息率、目標到達までの平均手数、1 手あたりの思考時間、最大連鎖の分布
- 8 手以内の全消しは評価対象から除外（書籍と同じ）

シードは `--seed` から連番なので、同じ条件なら AI 同士を同じツモで比較できる。

## AI と成績

とこぷよ・AC ツモ・NEXT2 まで表示・最大 50 手・目標 10 連鎖、シード 0〜99 の 100 ゲーム。

| AI | 10連鎖発火率 | 最大連鎖 中央値 | 思考時間 |
|---|---|---|---|
| random | 0% | 2 | 0.03 ms/手 |
| greedy | 0% | 2 | 0.6 ms/手 |
| lookahead | 25% | 9 | 約 140 ms/手 |

### lookahead（`puyo/ai/lookahead.py`）

- 手持ち＋NEXT1＋NEXT2 の 3 手を全探索し、**見えているツモだけで発火できる最大連鎖（ポテンシャル）** を求める
- 評価 = ポテンシャル（連鎖数×1000 ＋ 得点/100）＋ 形（2・3 連結の加点、U 字からのずれの減点）− ちぎり
- 目標（`fire`、既定 10）以上の連鎖が今撃てるなら撃つ。それ未満は撃たずに温存して伸ばす
- 窒息が近いとき、または残り手数が見えている範囲で尽きるときは、その時点の最大連鎖を撃つ
- パラメータは `--opt w_shape=3` のように変更できる（一覧はファイル冒頭の docstring）

## 自作 AI の書き方

`examples/my_ai.py` をコピーして `decide()` を実装する。

```python
class MyAI(AI):
    def decide(self, state: GameState) -> Move:
        for move in state.legal_moves():
            field, chain, tear = simulate(state.field, state.current, move)
            ...
        return best_move
```

```sh
.venv/bin/python -m puyo bench --ai examples.my_ai:MyAI -n 100
```

- `GameState`: `field`（コピー）/ `current` / `nexts`（NEXT1, NEXT2）/ `hand` / `score` / `hands_left`（残り手数）
- `Move(x, rot)`: `x` は軸ぷよの列 1〜6、`rot` は子ぷよの向き 0=上 1=右 2=下 3=左
- `simulate(field, pair, move)` → `(置いて連鎖した後の Field, ChainResult, ちぎり段差)`（非破壊）
- `Field.parse("...")` で書籍表記（上の段から `R G B Y O .`、改行か `/` 区切り）の盤面を作れる

## 構成

```
puyo/
  core.py     フィールド・組ぷよ・設置・連鎖・得点（ぷよぷよ通ルール）
  tsumo.py    ツモ生成（AC 通風: 128 手で 4 色均等・最初 3 手は 3 色）
  game.py     とこぷよ進行と AI への観測（GameState）
  bench.py    並列ベンチマークと集計
  replay.py   リプレイ JSON / HTML 出力
  viewer.html リプレイビューア（← → でフレーム、↑ ↓ で手、Space で再生）
  ai/         random（下限）、greedy（1 手読み）、lookahead（見えているツモで発火できる最大連鎖を評価）
examples/my_ai.py  自作 AI のテンプレート
tests/            ルール実装のテスト
```

## ルールの実装範囲と簡略化

- 6 列 × 13 段。(3,12) が埋まると窒息。13 段目は連鎖に参加しないが、下が消えれば落ちてくる
- 得点は通の計算式（連鎖ボーナス・連結ボーナス・色数ボーナス）。落下ボーナスは未実装
- おじゃまぷよは隣接消去に対応。`Field.drop_ojama()` で降らせられる（とこぷよでは未使用）
- **簡略化**: 14 段目に行くぷよは消滅。列の移動は「経路上の列の 13 段目が空いていれば通れる」とし、回しによる 13 段越えは考慮しない。操作フレーム数は計測しない（ちぎり段差のみ返す）

## 速度の目安

素の Python 実装で 1 手のシミュレーションが、発火しない手は約 4µs（置いたぷよが 4 つつながらなければ連鎖処理を省略）、5 連鎖で約 80µs。ビームサーチなどで足りなくなったら、`core.py` をビットボード化・Rust/C 拡張化する。
