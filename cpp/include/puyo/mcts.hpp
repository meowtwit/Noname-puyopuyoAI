// 見えないツモを反復ごとに推測し直す MCTS（open-loop：木は手の並びだけで持つ）。
//
// 1 反復:
//   1. 見えていない先のツモを推測する
//   2. 根から UCB で手を選んで進む。子の事前値（評価関数）を 1 回分の訪問として混ぜる
//   3. 未展開のノードに着いたら展開し、全ての子を評価関数で採点。その最大値を反復の値とする
//      （連鎖が起きた子は撃った連鎖の値、窒息した子は大きな負の値）
//   4. 通ってきた (ノード, 手) に値を足す
// 手の候補は progressive widening で事前値の高い順に少しずつ広げる（木を深くするため）。
// 最後に訪問回数が最大の初手を選ぶ。値の単位は「連鎖数」（評価値 / w_chain）。
#pragma once

#include <array>
#include <map>
#include <memory>
#include <string>
#include <vector>

#include "eval.hpp"
#include "sampler.hpp"

namespace puyo {

struct MctsOptions {
    int iterations = 1500;
    int depth = 12;
    double c = 1.0;  // UCB の探索係数（連鎖数の単位）
    int fire = 10;
    // progressive widening: 訪問回数 N のノードでは事前値の上位 ceil(pw_k * (N+1)^pw_alpha) 手だけを選ぶ
    double pw_k = 2.0;
    double pw_alpha = 0.5;
    // 目標未満の連鎖を撃ったときの値の割引（撃つとその連鎖は失われるため）。残り手数が少ないときは割引しない
    double small_fire = 0.1;
    EvalOptions eval;

    static MctsOptions from_map(const std::map<std::string, double>& m);
};

class MctsAI {
public:
    MctsAI(MctsOptions opt, uint64_t seed) : opt_(opt), ev_(opt.eval), sampler_(seed) {}

    Move decide(const Field& field, const std::vector<Pair>& known, int hands_left,
                const std::array<int, 4>* remaining);

    // 直前の decide の根の訪問回数（デバッグ・可視化用。all_moves() の順）
    const std::array<int, 22>& root_visits() const { return root_visits_; }

    static constexpr int N_MOVES = 22;
    struct Node {
        bool expanded = false;
        std::array<int, N_MOVES> n{};
        std::array<double, N_MOVES> w{};
        std::array<double, N_MOVES> prior{};
        std::array<int8_t, N_MOVES> order{};  // 事前値の高い順の手
        int n_order = 0;
        int visits = 0;
        std::array<std::unique_ptr<Node>, N_MOVES> child;
    };

private:
    // field に対して pair を置く合法手（all_moves() の添字）
    static void legal_indices(const Field& field, const Pair& pair, std::vector<int>& out);
    double value_of(const SimResult& s, bool last, bool endgame) const;
    double expand(Node& node, const Field& field, const Pair& pair, bool last, bool endgame) const;

    MctsOptions opt_;
    Evaluator ev_;
    TsumoSampler sampler_;
    std::array<int, 22> root_visits_{};
};

}  // namespace puyo
