#include "puyo/lookahead.hpp"

#include <limits>
#include <stdexcept>

#include "puyo/detect.hpp"

namespace puyo {

namespace {

// U 字の理想形（平均高さからのずれ）。Python 版と同じ値
constexpr double U_SHAPE[WIDTH] = {2.0, 0.5, -1.0, -1.0, 0.0, 1.5};
const Bits VISIBLE = Bits::rect(1, VISIBLE_HEIGHT);

}  // namespace

LookaheadOptions LookaheadOptions::from_map(const std::map<std::string, double>& m) {
    LookaheadOptions o;
    for (const auto& [k, v] : m) {
        if (k == "fire") o.fire = static_cast<int>(v);
        else if (k == "w_chain") o.w_chain = v;
        else if (k == "conn2") o.conn2 = v;
        else if (k == "conn3") o.conn3 = v;
        else if (k == "w_shape") o.w_shape = v;
        else if (k == "w_tear") o.w_tear = v;
        else if (k == "danger") o.danger = static_cast<int>(v);
        else if (k == "detect_depth") o.detect_depth = static_cast<int>(v);
        else if (k == "w_need") o.w_need = v;
        else if (k == "w_block") o.w_block = v;
        else throw std::invalid_argument("unknown option: " + k);
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
            else if (free_fire) val = chain_value(s.chain.chains, s.chain.score);
            else val = -1e6 + s.chain.score;
        } else {
            auto [pc, ps] = potential(s.field, pairs.data() + 1, n - 1);
            double pot = std::max(chain_value(pc, ps), virtual_value(s.field, pairs.data() + 1, n - 1, opt_.detect_depth));
            val = pot + shape(s.field) - opt_.w_tear * s.tear;
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
    double best = 0.0;
    bool any = false;
    for_each_trigger(field, [&](const Trigger& t) {
        if (!field.is_reachable(Move{static_cast<int8_t>(t.x), 0})) return;  // 起爆点に組ぷよが届くこと
        double v = chain_value(t.chains, t.score) - opt_.w_need * t.need;
        if (!any || v > best) best = v;
        any = true;
    });
    if (depth >= 2 && n > 0) {
        for (Move move : legal_moves(field, pairs[0])) {
            SimResult s = simulate(field, pairs[0], move);
            if (s.chain.chains || s.field.is_dead()) continue;
            best = std::max(best, virtual_value(s.field, pairs + 1, n - 1, depth - 1));
        }
    }
    return best;
}

double LookaheadAI::shape(const Field& field) const {
    double score = 0.0;
    for (Color c : NORMAL_COLORS) {
        Bits rest = field.plane(c) & VISIBLE;
        // 孤立したぷよは連結の計算を省く
        Bits single = rest.andnot(rest.neighbors());
        rest = rest.andnot(single);
        while (!rest.empty()) {
            Bits g = rest.lowest().expand(rest);
            int k = g.popcount();
            score += k == 2 ? opt_.conn2 : opt_.conn3;
            rest = rest.andnot(g);
        }
    }
    int hs[WIDTH];
    double sum = 0;
    for (int x = 1; x <= WIDTH; ++x) sum += hs[x - 1] = field.height(x);
    double avg = sum / WIDTH;
    double dev = 0;
    for (int i = 0; i < WIDTH; ++i) {
        double d = hs[i] - avg - U_SHAPE[i];
        dev += d * d;
    }
    score -= opt_.w_shape * dev;
    int blocked = 0;
    for (int i = 1; i <= 4; ++i) blocked += hs[i] >= 12;
    score -= opt_.w_block * blocked;
    return score;
}

bool LookaheadAI::survivable(const Field& field, const Pair& pair) {
    for (Move move : legal_moves(field, pair))
        if (!simulate(field, pair, move).field.is_dead()) return true;
    return false;
}

}  // namespace puyo
