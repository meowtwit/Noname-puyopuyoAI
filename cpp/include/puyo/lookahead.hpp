// Python の puyo/ai/lookahead.py の C++ 版。同じ盤面・同じオプションなら同じ手を選ぶ。
#pragma once

#include <map>
#include <string>
#include <utility>
#include <vector>

#include "eval.hpp"

namespace puyo {

struct LookaheadOptions {
    int fire = 10;
    double w_tear = 5;
    int danger = 54;
    int detect_depth = 2;
    EvalOptions eval;

    static LookaheadOptions from_map(const std::map<std::string, double>& m);
};

class LookaheadAI {
public:
    explicit LookaheadAI(LookaheadOptions opt = {}) : opt_(opt), ev_(opt.eval) {}

    // pairs[0] が手持ち、以降が NEXT。hands_left < 0 は無制限
    Move decide(const Field& field, std::vector<Pair> pairs, int hands_left) const;

    std::pair<int, int> potential(const Field& field, const Pair* pairs, int n) const;
    double virtual_value(const Field& field, const Pair* pairs, int n, int depth) const;
    bool in_danger(const Field& field) const { return field.count() >= opt_.danger || field.height(3) >= 10; }

private:
    LookaheadOptions opt_;
    Evaluator ev_;
};

// pair を死なずに置ける手があるか
bool survivable(const Field& field, const Pair& pair);

}  // namespace puyo
