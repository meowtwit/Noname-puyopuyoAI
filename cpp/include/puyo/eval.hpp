// 盤面の評価関数（lookahead / beam / mcts で共用）。
//
//   eval(f) = trigger_value(f) + shape(f)
//   trigger_value : 色ぷよを足せば起きる連鎖の最大評価（連鎖数×w_chain + 得点/100 − 足りない個数×w_need）
//   shape         : 2・3 連結の加点、U 字からのずれ² と通路（2〜5 列目）の 12 段以上を減点
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
    double eval(const Field& field) const { return trigger_value(field) + shape(field); }

private:
    EvalOptions opt_;
};

}  // namespace puyo
