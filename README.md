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
| `--ai` | greedy | `random` / `greedy` / `lookahead` / `lookahead_cpp` / `beam_cpp` / `mcts_cpp` / `versus_cpp` / `モジュール:クラス` |
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

見えないツモを推測して読む AI（C++ のみ、既定のオプション、シード 0〜199 の 200 ゲーム）:

| AI | 目標 10 連鎖（50 手）発火率 | 目標 14 連鎖（60 手、`fire=14`）発火率 | 思考時間 |
|---|---|---|---|
| lookahead_cpp | 51% | 1.8%（中央値 10） | 1.5 ms/手 |
| **beam_cpp** | **99.5%**（窒息 0%） | **30.5%**（中央値 12、窒息 3%） | 約 180 ms/手 |
| mcts_cpp（`small_fire=0`） | 63% | – | 約 90 ms/手 |

### lookahead（`puyo/ai/lookahead.py`）

- 手持ち＋NEXT1＋NEXT2 の 3 手を全探索し、**見えているツモだけで発火できる最大連鎖** を求める
- さらに今の手の後・NEXT1 の後の盤面で、**色ぷよを 1〜3 個足せば起きる連鎖**（`puyo/detect.py`、書籍の RensaDetector 相当）を調べる。足りない個数だけ減点し、起爆点に組ぷよが届く列に限る
- ポテンシャル = 上の 2 つの大きい方（連鎖数×1000 ＋ 得点/100）
- 評価 = ポテンシャル ＋ 形（2・3 連結の加点、U 字からのずれ・通路の列を 12 段以上にすることの減点）− ちぎり。次の組ぷよで詰む手は大きく減点
- 目標（`fire`、既定 10）以上の連鎖が今撃てるなら撃つ。それ未満は撃たずに温存して伸ばす
- 窒息が近いとき、または残り手数が見えている範囲で尽きるときは、その時点の最大連鎖を撃つ
- パラメータは `--opt w_shape=3` のように変更できる（一覧はファイル冒頭の docstring）

### beam_cpp（`cpp/src/beam.cpp`）: 見えないツモの期待値ビームサーチ

1. NEXT2 より先のツモを `samples` 通り推測する（下の「ツモの推測」）
2. それぞれのツモ列で幅 `width`・深さ `depth` のビームサーチ。連鎖が起きた枝はそこで打ち切ってその連鎖を記録し、起きなければ評価関数（連鎖検出＋形）の上位 `width` 個を残す。同じ盤面は 1 つにまとめる
3. 初手ごとに「子孫が到達した最大の評価」を記録し、ツモ列全体で平均した期待値が最大の初手を選ぶ
4. 目標（`fire`）以上が今撃てるなら撃つ。残り手数が探索の深さ以内なら、撃った連鎖だけを評価する

オプション: `width`（40）`depth`（10）`samples`（8）`fire`（10）`small_fire`（1.0：目標未満の連鎖を撃ったときの割引）＋評価関数の重み

### mcts_cpp（`cpp/src/mcts.cpp`）: open-loop MCTS

- 反復ごとに先のツモを推測し直し、木は「手の並び」だけで持つ（ツモが違っても同じ手の統計を共有）
- ノードを展開するときに全ての子を評価関数で採点し、事前値として 1 回分の訪問に混ぜる。反復の値はその最大値
- progressive widening（`pw_k`・`pw_alpha`）で事前値の上位の手から少しずつ候補を広げ、木を深くする
- 目標未満の連鎖を撃った値は `small_fire`（既定 0.1）で割り引く。割り引かないと「読むほど小連鎖を撃ちたがる」（撃った連鎖は確定値、伸ばす価値はツモの平均で低めに出るため）
- オプション: `iterations`（1500）`depth`（12）`c`（1.0）`pw_k`（2）`pw_alpha`（0.5）`small_fire`（0.1）`fire`（10）＋評価関数の重み

### ツモの推測（`cpp/include/puyo/sampler.hpp`）

AC 通は 128 手で各色 64 個なので、AI はこれまでに見たツモを数え、今の周期で残っている色から非復元抽出で引く（`--opt tsumo_model=ac`、既定）。`tsumo_model=uniform` なら各色 1/4 の独立抽選。

### 評価関数（`cpp/src/eval.cpp`）

3 つの AI で共通。`eval = 連鎖検出の最大値（連鎖数×w_chain＋得点/100−足りない個数×w_need）＋形（conn2・conn3 の加点、U 字からのずれ²×w_shape と通路を塞ぐ形×w_block の減点）`。

## 対戦（`python -m puyo versus` / `vplay`）

```sh
python -m puyo versus --ai1 versus_cpp --ai2 beam_cpp --opt2 fire=10 -n 100   # 勝率（95% 信頼区間つき）
python -m puyo vplay  --ai1 versus_cpp --ai2 beam_cpp --opt2 fire=10 -n 20 --open   # 20 局のリプレイ＋一覧ページ
python -m puyo vplay  ... -n 1 --seed 2 -o replays/one.html                          # 1 局だけ
```

`vplay` は既定で 20 局を並列に作り、`replays/<名前>/index.html`（勝者・手数・最大連鎖・「誰が何連鎖で何個送ったか」の流れ）と、
全セットをまとめた `replays/index.html` を更新する。

```sh
```

### ルール（`puyo/versus.py`）

- 2 人とも同じツモ列。時間はフレームで進む: 1 手 40f（ちぎり +20f）、連鎖 1 段 60f、おじゃま落下 30f（書籍の「N 連鎖の間に約 1.5N 手置ける」に合わせた値。`--hand-frames` `--chain-frames` で変更可）
- 連鎖の各段の得点を 70 点で 1 個のおじゃまに換算（端数は持ち越し）。自分に来る予定のおじゃまがあれば先に相殺し、残りを相手へ
- **おじゃまは、相手の連鎖がすべて終わった後に置いた 1 手の後に降る**（その手で自分が連鎖したら連鎖の後）。1 回に最大 6 段（36 個、`--max-rows`）、残りは次の手の後
- 3 列目の 12 段目が埋まったら負け。250 手（`--max-hands`）で引き分け。奇数シードは左右を入れ替えて有利不利を打ち消す
- AI には `GameState.versus`（`VersusInfo`）で、相手の盤面・来るおじゃまの見込み・降るまでに置ける手数（`window`）・相手の次のツモなどが渡る
- 簡略化: 全消しボーナス、相殺による連鎖中の予告の細かい挙動、操作のフレーム差（回し・高さによる落下時間）は再現していない

### versus_cpp（`cpp/src/versus.cpp`）: 打ち返し AI

基本戦略は「自分からは撃たずに組み、相手が発火したら降るまでに打ち返す」。

1. **倒せるなら撃つ**: 送るおじゃま ≥ 相手の 3 列目を埋める量 ＋ 相手が打ち返せる量 ＋ `kill_margin`（30）。
   相手が打ち返せる量は、**相手の立場でビームサーチ**して「自分の連鎖が終わるまでに相手が撃てる最大のおじゃま」を見積もる
2. **打ち返し**: 来るおじゃまが `accept`（6）個を超え、降るまでの手数（相手の連鎖が終わるまでの手数 ＋ 1）がビームの深さ以内なら、
   その手数の中で「送り返すおじゃま − 来るおじゃま」が最大になる発火をビームサーチで探す（撃たずに受けるのも候補）
3. それ以外はとこぷよの beam と同じく組む（`fire` の既定は 99 = 連鎖数だけでは撃たない。盤面が埋まると撃つ枝しか残らず自然に撃つ）
4. **2 本目**: 打ち返しの発火を選ぶとき、撃った後に残る連鎖の見込みも `residual`（0.5）の割合で加点する。
   相手に返されても、その返しが降るまでに 2 本目を撃って返し返すため（リプレイでは 11→10→11→10 のような撃ち合いが出る）
5. **潰し**（既定は無効、`--opt crush=1`）: 見えている 3 手の中で 3 連鎖以下・12 個以上を送れる発火を最短で撃つ。
   `crush_check` で相手の返しを見積もるか（0: 見ない / 1: 相手に見えているツモだけ / 2: 先のツモも推測）、`crush_until` で何手目まで潰すかを決める

潰しの検証（60 局。相手は潰しも 2 本目もなしの versus_cpp）:

| 設定 | 勝率 |
|---|---|
| 潰し最速（`crush=1 crush_check=0 crush_until=8`） | 33% |
| 12 手目まで判定なしで潰す | 20% |
| 試合中ずっと判定なしで潰す | 7% |
| 判定あり（`crush_check=1`／`2`） | 40%（潰しがほぼ出ず、五分） |

打ち返さない beam（10 連鎖で撃つ）が相手だと、潰し最速 87%・潰しなし 90% で差は誤差程度。
この環境では 3 連鎖の潰しが届くまでに相手は 5〜6 手置け、相手の AI は常に「すぐ撃てる小連鎖」を持つ形で組んでいるため、より大きな小連鎖で返されてしまう。

| 対戦（100 局） | versus_cpp の勝率 |
|---|---|
| vs beam_cpp（10 連鎖以上が撃てたら撃つ） | **83%** ± 7% |
| vs beam_cpp（12 連鎖以上が撃てたら撃つ） | **72%** ± 9% |
| vs versus_cpp（同じ AI、60 局） | 40% ± 12%（五分の範囲） |
| vs beam_cpp（10 連鎖）、2 本目あり（現在の既定、60 局） | 90% ± 8% |

改良前（倒せる量の見積もりが「今の盤面にぷよを数個足す」程度だった版）は vs beam（10）で 52.5%。先に 8 連鎖を撃ち、相手にその間の約 13 手で 11 連鎖を組まれて返される負け方が多かった。

## パラメータ自動調整（`python -m puyo tune`）

Optuna（TPE）で AI のオプションを調整する（`pip install optuna`）。

```sh
# beam を 14 連鎖目標で調整。--opt で渡したものは固定し、それ以外（探索空間 beam）を探す
python -m puyo tune --ai beam_cpp --space beam --trials 30 -n 100 --target 14 --hands 60 \
    --opt fire=14 --opt width=20 --opt samples=4
```

- 全試行で同じシードを使い、パラメータの差だけを比べる。1 試行目は既定値
- 終了後、上位 `--top` 個と既定値を **学習に使っていない別のシード**（`--validate` ゲーム）で再評価し、最良の `--opt ...` を表示する（学習用シードでの値は過学習で高めに出るため）
- 探索空間は `puyo/tune.py` の `SPACES`（`eval` / `lookahead` / `beam` / `mcts`）。履歴は `results/optuna.db` に残り、同じ `--study` で再開できる

例:
- lookahead_cpp を 10 連鎖目標で 25 試行（各 300 ゲーム、約 2 分）→ 検証用 1000 ゲームで発火率 51.0% → **62.5%**
- beam_cpp を 14 連鎖目標（60 手）で 30 試行（軽量設定 width=20・samples=4、各 100 ゲーム、約 25 分）→ 検証用 200 ゲームで 13.0% → 15.5%。
  その重みをフル設定（width=40・samples=8）で使うと、シード 0〜199 で **30.5% → 35.0%**（中央値 12 → 13）、ただし窒息 3% → 7%

  ```
  --opt fire=14 --opt w_need=366 --opt conn2=7.5 --opt conn3=48.29 --opt w_shape=15.11 --opt w_block=1307 --opt small_fire=0.9749
  ```

注意: 目的関数を発火率だけ（`--objective rate`）にすると、「死んでもいいから一発狙い」のパラメータが選ばれる（beam で検証時の窒息率 54.5%）。既定の `safe` は窒息率を引く。

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
  ai/sampling_cpp.py   beam_cpp / mcts_cpp / versus_cpp の呼び出し（ツモの数え上げ）
  versus.py            対戦エンジン（時間・おじゃま・相殺）と対戦の実行
  versus_viewer.html   対戦リプレイのビューア（#t=フレーム でその時刻へ）
  tune.py              パラメータ自動調整
cpp/
  include/puyo/bits.hpp   ビットボード（SIMD バックエンドの切り替え）
  src/field.cpp           設置・連鎖・得点
  src/detect.cpp          連鎖の検出
  src/eval.cpp            評価関数（3 つの AI で共通）
  src/lookahead.cpp       lookahead AI
  src/beam.cpp            期待値ビームサーチ
  src/mcts.cpp            open-loop MCTS
  src/versus.cpp          対戦用 AI（打ち返し）
  include/puyo/sampler.hpp  見えないツモの推測
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
