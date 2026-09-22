#include "puyo/versus.hpp"

#include <algorithm>
#include <stdexcept>

#include "puyo/detect.hpp"

namespace puyo {

namespace {

// 打ち返し探索の値: 送り返すおじゃま − 来るおじゃま。撃たずに降るまでの手数を使い切ったら全部受ける
struct CounterValue : BeamValue {
    int incoming, carry;
    double w;
    CounterValue(int in, int c, double w_) : incoming(in), carry(c), w(w_) {}
    double fired(int, int score) const override { return ((score + carry) / OJAMA_RATE - incoming) * w; }
    double leaf(double e, bool last) const override { return last ? -incoming * w + e * 0.01 : BEAM_NONE; }
};

}  // namespace

VersusOptions VersusOptions::from_map(const std::map<std::string, double>& m) {
    VersusOptions o;
    for (const auto& [k, v] : m) {
        if (k == "accept") o.accept = static_cast<int>(v);
        else if (k == "w_ojama") o.w_ojama = v;
        else if (k == "counter_need") o.counter_need = static_cast<int>(v);
        else if (k == "kill_margin") o.kill_margin = static_cast<int>(v);
        else if (!o.beam.set(k, v)) throw std::invalid_argument("unknown option: " + k);
    }
    return o;
}

int VersusAI::counter_potential(const Field& opponent) const {
    int best = 0;
    for_each_trigger(opponent, [&](const Trigger& t) { best = std::max(best, t.score / OJAMA_RATE); },
                     opt_.counter_need);
    return best;
}

int VersusAI::opponent_counter(const Field& opponent, const std::vector<Pair>& opp_pairs, int window) {
    int best = counter_potential(opponent);
    // 相手の手持ちが分からなければ、推測した 1 手目から探す
    std::vector<Pair> known = opp_pairs;
    if (known.empty()) known = beam_.sample_pairs(1);
    std::vector<Move> legal = legal_moves(opponent, known[0]);
    if (legal.empty()) return best;
    const int depth = std::max(1, std::min(window, opt_.beam.depth));
    std::vector<double> v = beam_.expected_values(opponent, legal, known, depth, nullptr,
                                                  CounterValue(0, 0, opt_.w_ojama));
    return std::max(best, static_cast<int>(*std::max_element(v.begin(), v.end()) / opt_.w_ojama));
}

Move VersusAI::decide(const Field& field, const std::vector<Pair>& known, const std::array<int, 4>* remaining,
                      const VersusContext& ctx, const Field& opponent) {
    std::vector<Move> legal = legal_moves(field, known.at(0));
    auto ojama = [&](int score) { return (score + ctx.carry) / OJAMA_RATE; };

    // 1. 倒せる / 目標以上なら撃つ（送るおじゃまが最大の手）
    const int base_kill = lethal(opponent) + opt_.kill_margin;
    int best = -1, best_net = 0, longest = 0;
    std::vector<std::pair<int, int>> cands;  // (legal の添字, 送るおじゃま)
    for (size_t i = 0; i < legal.size(); ++i) {
        SimResult s = simulate(field, known[0], legal[i]);
        if (!s.chain.chains || s.field.is_dead()) continue;
        int net = ojama(s.chain.score) - ctx.incoming;
        if (s.chain.chains >= opt_.beam.fire && (best < 0 || net > best_net)) {
            best = static_cast<int>(i);
            best_net = net;
        }
        if (net >= base_kill) {
            cands.emplace_back(static_cast<int>(i), net);
            longest = std::max(longest, s.chain.chains);
        }
    }
    if (best >= 0) return legal[best];
    if (!cands.empty()) {
        // 自分の連鎖が終わるまで（＋降るまでの 1 手）に相手が置ける手数で、相手が打ち返せる量を見積もる
        const int opp_window = (longest * ctx.chain_frames + ctx.hand_frames - 1) / ctx.hand_frames + 1;
        const int kill = base_kill + opponent_counter(opponent, ctx.opp_pairs, opp_window);
        for (auto [i, net] : cands)
            if (net >= kill && (best < 0 || net > best_net)) {
                best = i;
                best_net = net;
            }
        if (best >= 0) return legal[best];
    }

    // 2. 打ち返し
    if (ctx.incoming > opt_.accept && ctx.window >= 1 && ctx.window <= opt_.beam.depth) {
        std::vector<double> v = beam_.expected_values(field, legal, known, ctx.window, remaining,
                                                      CounterValue(ctx.incoming, ctx.carry, opt_.w_ojama));
        size_t arg = 0;
        for (size_t i = 1; i < legal.size(); ++i)
            if (v[i] > v[arg]) arg = i;
        if (v[arg] > BEAM_NONE) return legal[arg];
    }

    // 3. 組む
    return beam_.decide(field, known, -1, remaining);
}

}  // namespace puyo
