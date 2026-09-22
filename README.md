# PuyopuyoAI

ぷよぷよ（通ルール）で **とこぷよ 10 連鎖** を安定して打てる AI を作るための試験環境。
ルールと評価方法は「第１回ぷよぷよ人類vsAI」（puyoai / mayah）を参考にしている。

## セットアップ

```sh
python3 -m venv .venv
.venv/bin/pip install pytest
.venv/bin/python -m pytest        # ルール実装のテスト
```

Python 版だけなら外部ライブラリは不要（Python 3.11+）。C++ 版（高速）は下の「C++ 版」を参照。

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
| `--ai` | greedy | `random` / `greedy` / `lookahead` / `lookahead_cpp` / `モジュール:クラス` |
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
| lookahead（detect_depth=0：見えているツモのみ） | 25% | 9 | 約 140 ms/手 |
| lookahead（既定：仮想連鎖検出あり） | 49% | 9（平均 9.0、窒息 1%） | 約 540 ms/手 |
| lookahead_cpp（C++ 版。上と全ゲーム同一結果） | 49% | 9 | **1.5 ms/手** |

lookahead_cpp で 1000 ゲーム（シード 0〜999）: 発火率 51.0%、中央値 10、窒息 1.4%（8 秒）。

### lookahead（`puyo/ai/lookahead.py`）

- 手持ち＋NEXT1＋NEXT2 の 3 手を全探索し、**見えているツモだけで発火できる最大連鎖** を求める
- さらに今の手の後・NEXT1 の後の盤面で、**色ぷよを 1〜3 個足せば起きる連鎖**（`puyo/detect.py`、書籍の RensaDetector 相当）を調べる。足りない個数だけ減点し、起爆点に組ぷよが届く列に限る
- ポテンシャル = 上の 2 つの大きい方（連鎖数×1000 ＋ 得点/100）
- 評価 = ポテンシャル ＋ 形（2・3 連結の加点、U 字からのずれ・通路の列を 12 段以上にすることの減点）− ちぎり。次の組ぷよで詰む手は大きく減点
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

## C++ 版（ビットボード）

`cpp/` にコア（フィールド・連鎖・検出）と lookahead AI の C++20 実装がある。Python 版と **同じ入力なら同じ結果・同じ手** になるように作ってあり、テストで常に突き合わせている。

- フィールドは書籍 3 章と同じ 128bit（8 列 × 16 段）× 3 面の色コード
- 消去判定は隣接数のビット演算で「4 つ以上つながる種」を求めて広げる（puyoai の vanishingSeed と同じ考え方）
- SIMD はビルド時に選択:

| `--simd` | 用途 | 中身 |
|---|---|---|
| `AVX2`（x86_64 の既定） | Windows / Linux の本番 | 128bit 面は `__m128i`、4 色の消去判定は `__m256i` で 2 色ずつ同時に。落下は BMI2 `pext` |
| `SSE2` | 古い x86_64 | `__m128i` のみ |
| `PORTABLE`（ARM の既定） | Apple Silicon など | `uint64_t × 2` |
| `SIMDE` | 検証用 | SIMDe で AVX2 の経路を ARM 上でエミュレート |

速度の目安（M1）: `simulate` 約 70 ns/回（Python 版の 50〜1000 倍）、lookahead 1 手 約 1 ms（Python 版の約 500 倍）。

### ビルド（macOS / Linux）

```sh
.venv/bin/pip install pybind11
.venv/bin/python scripts/build_cpp.py --selftest   # puyo/_puyocpp.* ができ、C++ 単体テストも走る
.venv/bin/python -m pytest                         # Python 版との一致テスト（tests/test_cpp.py）を含む
.venv/bin/python -m puyo bench --ai lookahead_cpp -n 1000
```

### ビルド（Windows・AVX2）

事前に Visual Studio 2022（「C++ によるデスクトップ開発」）と Python 3.11+ を入れる。CMake は VS 付属のものか `pip install cmake` で入れたもの。

```powershell
py -m venv .venv
.venv\Scripts\pip install pytest pybind11 cmake
.venv\Scripts\python scripts\build_cpp.py --selftest    # x64 なら自動で AVX2（/arch:AVX2）
.venv\Scripts\python -m pytest
.venv\Scripts\python -m puyo bench --ai lookahead_cpp -n 1000
```

`selftest` の 1 行目が `backend: avx2+bmi2`、2 行目が `OK (0 failures)` になれば、AVX2 版が Python 版と同じ動きをしている。

### 検証のしくみ

- `scripts/gen_fixtures.py` が Python 版の結果から正解データ `tests/fixtures/cpp_fixtures.txt`（simulate 約 7800 件・detect 約 1700 件・lookahead の判断 256 件）を作る
- `selftest`（C++ のみ）がその正解データと照合する。Python を変えたら fixtures を作り直す
- macOS 上での確認状況: portable（arm64）・SSE2（Rosetta 上の x86_64）・AVX2（SIMDe でのエミュレーション）で全件一致。BMI2 `pext` の実機動作は Windows で `selftest` を実行して確認する

## 構成

```
puyo/
  core.py     フィールド・組ぷよ・設置・連鎖・得点（ぷよぷよ通ルール）
  tsumo.py    ツモ生成（AC 通風: 128 手で 4 色均等・最初 3 手は 3 色）
  game.py     とこぷよ進行と AI への観測（GameState）
  detect.py   連鎖の検出（色ぷよを足して起きる連鎖を列挙）
  bench.py    並列ベンチマークと集計
  replay.py   リプレイ JSON / HTML 出力
  viewer.html リプレイビューア（← → でフレーム、↑ ↓ で手、Space で再生）
  ai/         random（下限）、greedy（1 手読み）、lookahead（見えているツモ＋仮想連鎖検出で評価）
  ai/lookahead_cpp.py  C++ 版 lookahead の呼び出し
cpp/
  include/puyo/bits.hpp   ビットボード（SIMD バックエンドの切り替え）
  src/field.cpp           設置・連鎖・得点
  src/detect.cpp          連鎖の検出
  src/lookahead.cpp       lookahead AI
  src/bindings.cpp        pybind11 モジュール
  tools/selftest.cpp      C++ 単体テスト＆ベンチ
scripts/build_cpp.py      C++ のビルド（全 OS 共通）
scripts/gen_fixtures.py   C++ 検証用の正解データを Python 版から作る
examples/my_ai.py  自作 AI のテンプレート
tests/            ルール実装のテスト、Python 版と C++ 版の一致テスト
```

## ルールの実装範囲と簡略化

- 6 列 × 13 段。(3,12) が埋まると窒息。13 段目は連鎖に参加しないが、下が消えれば落ちてくる
- 得点は通の計算式（連鎖ボーナス・連結ボーナス・色数ボーナス）。落下ボーナスは未実装
- おじゃまぷよは隣接消去に対応。`Field.drop_ojama()` で降らせられる（とこぷよでは未使用）
- **簡略化**: 14 段目に行くぷよは消滅。列の移動は「経路上の列の 13 段目が空いていれば通れる」とし、回しによる 13 段越えは考慮しない。操作フレーム数は計測しない（ちぎり段差のみ返す）

## 速度の目安

Python 版: 1 手のシミュレーションが、発火しない手で約 4µs（置いたぷよが 4 つつながらなければ連鎖処理を省略）、5 連鎖で約 80µs。
C++ 版: 約 70 ns（上の「C++ 版」を参照）。探索を重くする AI は C++ 側で書き、Python 版はルールの基準実装・テスト用として残す。
