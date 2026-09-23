// 盤面の評価関数（lookahead / beam / mcts で共用）。
//
//   eval(f) = trigger_value(f) + shape(f)
//   trigger_value : 色ぷよを足せば起きる連鎖の最大評価（連鎖数×w_chain + 得点/100 − 足りない個数×w_need
//                   − 無駄な連結（消える数 − 連鎖数×4）×w_waste − 連鎖の後に残るぷよ×w_junk）
//   shape         : 2・3 連結の加点、U 字からのずれ² と通路（2〜5 列目）の 12 段以上を減点
//   dual（w_dual > 0 のとき）: 本線と別に、対応用の小連鎖（dual_min_chain〜dual_max_chain 連鎖）の発火点を持っているか。
//                 小連鎖を撃った後も本線（5 連鎖以上）の評価が dual_keep 割以上残るなら、小連鎖のおじゃま（dual_cap まで）× w_dual
#pragma once

#include <string>

#include "field.hpp"

namespace puyo {

struct EvalOptions {
    double w_chain = 1000;
    double conn2 = 10;
    double conn3 = 30;
    double w_shape = 8;
    double w_need = 250;
    double w_block = 1500;
    double w_dual = 0;       // 対応用の小連鎖を別に持っていることの加点（おじゃま 1 個あたり）。0 なら計算しない
    int dual_min_chain = 2;
    int dual_max_chain = 4;
    double dual_keep = 0.8;
    int dual_cap = 30;
    // 盤面のぷよが max_puyos 個を超えたら 1 個ごとに w_over を減点（相手の連鎖中に伸ばす余地を残すため）。0 なら使わない
    int max_puyos = 0;
    double w_over = 200;
    // 連鎖の効率: 1 段 4 個ちょうどで消える連鎖ほど良い（同じ広さで長く組め、空きも残る）
    double w_waste = 0;  // 消えるぷよのうち「連鎖数 × 4」を超える分（5 個以上の連結）1 個あたりの減点
    double w_junk = 0;   // その連鎖を撃った後に残るぷよ 1 個あたりの減点

    // 評価関数のオプションなら設定して true
    bool set(const std::string& key, double value);
};

class Evaluator {
public:
    explicit Evaluator(EvalOptions opt = {}) : opt_(opt) {}

    const EvalOptions& options() const { return opt_; }
    double chain_value(int chains, int score) const { return opt_.w_chain * chains + score / 100.0; }
    double shape(const Field& field) const;
    // 起爆点に組ぷよが届く連鎖のうち最大の評価。1 つも無ければ 0
    double trigger_value(const Field& field) const;
    double eval(const Field& field) const;
    // 本線を残したまま撃てる小連鎖の最大おじゃま（無ければ 0）
    int dual_ojama(const Field& field) const;

private:
    EvalOptions opt_;
};

}  // namespace puyo
