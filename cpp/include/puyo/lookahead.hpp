// Python の puyo/ai/lookahead.py の C++ 版。同じ盤面・同じオプションなら同じ手を選ぶ。
#pragma once

#include <map>
#include <string>
#include <utility>
#include <vector>

#include "field.hpp"

namespace puyo {

struct LookaheadOptions {
    int fire = 10;
    double w_chain = 1000;
    double conn2 = 10;
    double conn3 = 30;
    double w_shape = 8;
    double w_tear = 5;
    int danger = 54;
    int detect_depth = 2;
    double w_need = 250;
    double w_block = 1500;

    static LookaheadOptions from_map(const std::map<std::string, double>& m);
};

class LookaheadAI {
public:
    explicit LookaheadAI(LookaheadOptions opt = {}) : opt_(opt) {}

    // pairs[0] が手持ち、以降が NEXT。hands_left < 0 は無制限
    Move decide(const Field& field, std::vector<Pair> pairs, int hands_left) const;

    double chain_value(int chains, int score) const { return opt_.w_chain * chains + score / 100.0; }
    std::pair<int, int> potential(const Field& field, const Pair* pairs, int n) const;
    double virtual_value(const Field& field, const Pair* pairs, int n, int depth) const;
    double shape(const Field& field) const;
    bool in_danger(const Field& field) const { return field.count() >= opt_.danger || field.height(3) >= 10; }
    static bool survivable(const Field& field, const Pair& pair);

private:
    LookaheadOptions opt_;
};

}  // namespace puyo
