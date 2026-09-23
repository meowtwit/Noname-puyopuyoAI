#include "puyo/versus.hpp"

#include <algorithm>
#include <stdexcept>

#include "puyo/detect.hpp"

namespace puyo {

namespace {

// 打ち返し探索の値: 送り返すおじゃま − 来るおじゃま ＋ 撃った後に残る連鎖（2 本目）× residual。
// opp_counter > 0 なら、相殺しきって余った分からは相手が返してくる量を差し引く（相手が本線を残しているなら
// 本線で返すのは損 → 小連鎖で対応する）。撃たずに降るまでの手数を使い切ったら全部受ける
struct CounterValue : BeamValue {
    int incoming, carry;
    double w, residual;
    int opp_counter;
    double extend = 0;  // > 0 なら、読める範囲の終わりの盤面を「本線 × extend − 来る量」で評価する
    CounterValue(int in, int c, double w_, double r, int opp = 0, double ext = 0)
        : incoming(in), carry(c), w(w_), residual(r), opp_counter(opp), extend(ext) {}
    double fired(int, int score, const Field& after) const override {
        double v = (score + carry) / OJAMA_RATE - incoming;
        if (v > 0) v -= opp_counter;  // 余った分は相手の返しで相殺される
        if (residual > 0) v += residual * VersusAI::residual_ojama(after);
        return v * w;
    }
    double leaf(double e, bool last, const Field& field) const override {
        if (!last) return BEAM_NONE;
        if (extend > 0) {  // まだ降るまで手数がある: この盤面の本線を後から撃つ見込み
            double v = extend * VersusAI::main_ojama(field, 2) - incoming;
            if (v > 0) v -= opp_counter;
            return v * w + e * 0.01;
        }
        return -incoming * w + e * 0.01;
    }
};

// 潰し探索の値: 条件を満たす小連鎖を撃てたら送るおじゃま。それ以外は 0（形の良さを僅かに足す）
struct CrushValue : BeamValue {
    int carry, min_ojama, max_chain;
    double w;
    CrushValue(int c, int mn, int mx, double w_) : carry(c), min_ojama(mn), max_chain(mx), w(w_) {}
    double fired(int chains, int score, const Field&) const override {
        int o = (score + carry) / OJAMA_RATE;
        return chains <= max_chain && o >= min_ojama ? o * w : 0.0;
    }
    double leaf(double e, bool, const Field&) const override { return e * 1e-6; }
};

}  // namespace

VersusOptions VersusAI::default_options() {
    // w_dual（2 本立ての加点）は既定では使わない。30 で修正前の versus に 45%（五分）・計算は 2〜3 倍、
    // 100 では本線が弱くなり 28%。評価関数を dual_ojama などで調べるときの設定は dual_* を参照
    VersusOptions o;
    o.beam.eval.w_dual = 0;
    return o;
}

VersusOptions VersusOptions::from_map(const std::map<std::string, double>& m) {
    VersusOptions o = VersusAI::default_options();
    for (const auto& [k, v] : m) {
        if (k == "accept") o.accept = static_cast<int>(v);
        else if (k == "w_ojama") o.w_ojama = v;
        else if (k == "counter_need") o.counter_need = static_cast<int>(v);
        else if (k == "kill_margin") o.kill_margin = static_cast<int>(v);
        else if (k == "residual") o.residual = v;
        else if (k == "crush") o.crush = static_cast<int>(v);
        else if (k == "crush_min") o.crush_min = static_cast<int>(v);
        else if (k == "crush_max_chain") o.crush_max_chain = static_cast<int>(v);
        else if (k == "crush_depth") o.crush_depth = static_cast<int>(v);
        else if (k == "crush_check") o.crush_check = static_cast<int>(v);
        else if (k == "crush_until") o.crush_until = static_cast<int>(v);
        else if (k == "counter_opp") o.counter_opp = static_cast<int>(v);
        else if (k == "counter_width") o.counter_width = static_cast<int>(v);
        else if (k == "counter_samples") o.counter_samples = static_cast<int>(v);
        else if (k == "counter_depth") o.counter_depth = static_cast<int>(v);
        else if (k == "extend") o.extend = static_cast<int>(v);
        else if (k == "extend_discount") o.extend_discount = v;
        else if (k == "harass") o.harass = static_cast<int>(v);
        else if (k == "harass_min") o.harass_min = static_cast<int>(v);
        else if (k == "harass_min_chain") o.harass_min_chain = static_cast<int>(v);
        else if (k == "harass_max_chain") o.harass_max_chain = static_cast<int>(v);
        else if (k == "harass_keep") o.harass_keep = v;
        else if (k == "harass_ratio") o.harass_ratio = v;
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

std::tuple<int, double, int> VersusAI::crush_plan(const Field& field, const std::vector<Pair>& known,
                                                 const std::array<int, 4>* remaining, const VersusContext& ctx,
                                                 const Field& opponent) {
    std::vector<Move> legal = legal_moves(field, known.at(0));
    if (legal.empty()) return {-1, 0.0, 0};
    std::vector<double> v =
        beam_.expected_values(field, legal, known, std::max(1, opt_.crush_depth), remaining,
                              CrushValue(ctx.carry, opt_.crush_min, opt_.crush_max_chain, opt_.w_ojama));
    size_t arg = 0;
    for (size_t i = 1; i < legal.size(); ++i)
        if (v[i] > v[arg]) arg = i;
    const double expect = v[arg] / opt_.w_ojama;
    if (expect < opt_.crush_min) return {static_cast<int>(arg), expect, 0};
    // 相手が返すのに使える手数: 潰しの連鎖が終わるまで ＋ 降る前の 1 手
    if (opt_.crush_check == 0) return {static_cast<int>(arg), expect, 0};
    const int opp_window = (opt_.crush_max_chain * ctx.chain_frames + ctx.hand_frames - 1) / ctx.hand_frames + 1;
    return {static_cast<int>(arg), expect,
            opponent_counter(opponent, ctx.opp_pairs, opp_window, opt_.crush_check == 1)};
}

std::vector<double> VersusAI::counter_values(const Field& field, const std::vector<Pair>& known,
                                            const std::array<int, 4>* remaining, const VersusContext& ctx,
                                            const Field& opponent, int depth) {
    std::vector<Move> legal = legal_moves(field, known.at(0));
    const int opp = opt_.counter_opp ? counter_potential(opponent) : 0;
    return counter_beam_.expected_values(field, legal, known, depth, remaining,
                                         CounterValue(ctx.incoming, ctx.carry, opt_.w_ojama, opt_.residual, opp,
                                                      ctx.window > depth ? opt_.extend_discount : 0));
}

BeamOptions VersusAI::counter_options(const VersusOptions& o) {
    BeamOptions b = o.beam;
    b.eval.max_puyos = 0;  // 打ち返しでは残しておいた余白を使って伸ばす
    if (o.counter_width > 0) b.width = o.counter_width;
    if (o.counter_samples > 0) b.samples = o.counter_samples;
    if (o.counter_depth > 0) b.depth = o.counter_depth;
    return b;
}

int VersusAI::main_ojama(const Field& field, int min_chain) {
    int best = 0;
    for_each_trigger(field, [&](const Trigger& t) {
        if (t.chains >= min_chain && field.is_reachable(Move{static_cast<int8_t>(t.x), 0}))
            best = std::max(best, t.score / OJAMA_RATE);
    });
    return best;
}

int VersusAI::residual_ojama(const Field& field) {
    int best = 0;
    for_each_trigger(field, [&](const Trigger& t) { best = std::max(best, t.score / OJAMA_RATE); }, 2);
    return best;
}

int VersusAI::opponent_counter(const Field& opponent, const std::vector<Pair>& opp_pairs, int window,
                               bool visible_only) {
    int best = counter_potential(opponent);
    if (visible_only) {
        window = std::min(window, static_cast<int>(opp_pairs.size()));
        if (window <= 0) return best;
    }
    // 相手の手持ちが分からなければ、推測した 1 手目から探す
    std::vector<Pair> known = opp_pairs;
    if (known.empty()) known = beam_.sample_pairs(1);
    std::vector<Move> legal = legal_moves(opponent, known[0]);
    if (legal.empty()) return best;
    const int depth = std::max(1, std::min(window, opt_.beam.depth));
    std::vector<double> v = beam_.expected_values(opponent, legal, known, depth, nullptr,
                                                  CounterValue(0, 0, opt_.w_ojama, 0.0));
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

    // 2. 打ち返し（降るまでの手数で「送り返す − 来る」が最大になる発火を探す）
    const int cdepth = counter_beam_.options().depth;
    if (ctx.incoming > opt_.accept && ctx.window >= 1 && (ctx.window <= cdepth || opt_.extend)) {
        const int opp = opt_.counter_opp ? counter_potential(opponent) : 0;
        const bool beyond = ctx.window > cdepth;  // 読める範囲の後にもまだ手数がある
        std::vector<double> v = counter_beam_.expected_values(
            field, legal, known, std::min(ctx.window, cdepth), remaining,
            CounterValue(ctx.incoming, ctx.carry, opt_.w_ojama, opt_.residual, opp, beyond ? opt_.extend_discount : 0));
        size_t arg = 0;
        for (size_t i = 1; i < legal.size(); ++i)
            if (v[i] > v[arg]) arg = i;
        if (v[arg] > BEAM_NONE) return legal[arg];
    }

    // 3. 潰し（おじゃまが来ていないときだけ）
    if (opt_.crush && ctx.incoming == 0 && ctx.hand <= opt_.crush_until) {
        auto [arg, expect, opp] = crush_plan(field, known, remaining, ctx, opponent);
        // 相手が返せるなら潰さない（返されると自分が小さい連鎖しか持っていないため）
        if (arg >= 0 && expect >= opt_.crush_min && opp < expect) return legal[arg];
    }

    // 4. ちょっかい: 本線を残したまま小連鎖を撃ち、相手に本線を撃たせる（撃たなければ潰れる）
    if (opt_.harass && ctx.incoming == 0 && main_ojama(field) > 0) {
        const int opp_main = counter_potential(opponent);
        const int opp_response = beam_.evaluator().dual_ojama(opponent);  // 相手が本線を残したまま返せる量
        int best_h = -1, best_oj = 0;
        const int my_main = main_ojama(field);
        for (size_t i = 0; i < legal.size(); ++i) {
            SimResult s = simulate(field, known[0], legal[i]);
            if (s.chain.chains < opt_.harass_min_chain || s.chain.chains > opt_.harass_max_chain || s.field.is_dead())
                continue;
            const int oj = ojama(s.chain.score);
            if (oj < opt_.harass_min || oj <= best_oj || oj <= opp_response) continue;
            const int after = main_ojama(s.field);
            if (after >= opt_.harass_keep * my_main && after >= opt_.harass_ratio * opp_main) {
                best_h = static_cast<int>(i);
                best_oj = oj;
            }
        }
        if (best_h >= 0) return legal[best_h];
    }

    // 5. 組む
    return beam_.decide(field, known, -1, remaining);
}

}  // namespace puyo
