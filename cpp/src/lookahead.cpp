#include "puyo/lookahead.hpp"

#include <algorithm>
#include <limits>
#include <stdexcept>

namespace puyo {

LookaheadOptions LookaheadOptions::from_map(const std::map<std::string, double>& m) {
    LookaheadOptions o;
    for (const auto& [k, v] : m) {
        if (k == "fire") o.fire = static_cast<int>(v);
        else if (k == "w_tear") o.w_tear = v;
        else if (k == "danger") o.danger = static_cast<int>(v);
        else if (k == "detect_depth") o.detect_depth = static_cast<int>(v);
        else if (!o.eval.set(k, v)) throw std::invalid_argument("unknown option: " + k);
    }
    return o;
}

Move LookaheadAI::decide(const Field& field, std::vector<Pair> pairs, int hands_left) const {
    if (hands_left >= 0 && static_cast<int>(pairs.size()) > std::max(1, hands_left)) pairs.resize(std::max(1, hands_left));
    const int n = static_cast<int>(pairs.size());
    const bool free_fire = (hands_left >= 0 && hands_left <= n) || in_danger(field);

    std::vector<Move> legal = legal_moves(field, pairs[0]);
    Move best_move{};
    bool found = false;
    double best_val = -std::numeric_limits<double>::infinity();
    for (Move move : legal) {
        SimResult s = simulate(field, pairs[0], move);
        if (s.field.is_dead()) continue;
        double val;
        if (s.chain.chains) {
            if (s.chain.chains >= opt_.fire) val = 1e9 + s.chain.score;
            else if (free_fire) val = ev_.chain_value(s.chain.chains, s.chain.score);
            else val = -1e6 + s.chain.score;
        } else {
            auto [pc, ps] = potential(s.field, pairs.data() + 1, n - 1);
            double pot =
                std::max(ev_.chain_value(pc, ps), virtual_value(s.field, pairs.data() + 1, n - 1, opt_.detect_depth));
            val = pot + ev_.shape(s.field) - opt_.w_tear * s.tear;
            if (n > 1 && !survivable(s.field, pairs[1])) val -= 1e5;
        }
        if (val > best_val) {
            best_val = val;
            best_move = move;
            found = true;
        }
    }
    return found ? best_move : legal.at(0);
}

std::pair<int, int> LookaheadAI::potential(const Field& field, const Pair* pairs, int n) const {
    std::pair<int, int> best{0, 0};
    if (n <= 0) return best;
    for (Move move : legal_moves(field, pairs[0])) {
        SimResult s = simulate(field, pairs[0], move);
        if (s.field.is_dead()) continue;
        std::pair<int, int> cand;
        if (s.chain.chains) cand = {s.chain.chains, s.chain.score};
        else if (n > 1) cand = potential(s.field, pairs + 1, n - 1);
        else continue;
        if (cand > best) best = cand;
    }
    return best;
}

double LookaheadAI::virtual_value(const Field& field, const Pair* pairs, int n, int depth) const {
    if (depth <= 0) return 0.0;
    double best = ev_.trigger_value(field);
    if (depth >= 2 && n > 0) {
        for (Move move : legal_moves(field, pairs[0])) {
            SimResult s = simulate(field, pairs[0], move);
            if (s.chain.chains || s.field.is_dead()) continue;
            best = std::max(best, virtual_value(s.field, pairs + 1, n - 1, depth - 1));
        }
    }
    return best;
}

bool survivable(const Field& field, const Pair& pair) {
    for (Move move : legal_moves(field, pair))
        if (!simulate(field, pair, move).field.is_dead()) return true;
    return false;
}

}  // namespace puyo
