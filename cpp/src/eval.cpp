#include "puyo/eval.hpp"

#include <algorithm>

#include "puyo/detect.hpp"
#include "puyo/nn.hpp"

namespace puyo {

namespace {

// U 字の理想形（平均高さからのずれ）。Python 版と同じ値
constexpr double U_SHAPE[WIDTH] = {2.0, 0.5, -1.0, -1.0, 0.0, 1.5};
const Bits VISIBLE = Bits::rect(1, VISIBLE_HEIGHT);

}  // namespace

bool EvalOptions::set(const std::string& k, double v) {
    if (k == "w_chain") w_chain = v;
    else if (k == "w_dual") w_dual = v;
    else if (k == "dual_min_chain") dual_min_chain = static_cast<int>(v);
    else if (k == "dual_max_chain") dual_max_chain = static_cast<int>(v);
    else if (k == "dual_keep") dual_keep = v;
    else if (k == "dual_cap") dual_cap = static_cast<int>(v);
    else if (k == "max_puyos") max_puyos = static_cast<int>(v);
    else if (k == "w_over") w_over = v;
    else if (k == "w_waste") w_waste = v;
    else if (k == "w_junk") w_junk = v;
    else if (k == "w_nn") w_nn = v;
    else if (k == "w_base") w_base = v;
    else if (k == "conn2") conn2 = v;
    else if (k == "conn3") conn3 = v;
    else if (k == "w_shape") w_shape = v;
    else if (k == "w_need") w_need = v;
    else if (k == "w_block") w_block = v;
    else return false;
    return true;
}

double Evaluator::trigger_value(const Field& field) const {
    double best = 0.0;
    bool any = false;
    for_each_trigger(field, [&](const Trigger& t) {
        if (!field.is_reachable(Move{static_cast<int8_t>(t.x), 0})) return;  // 起爆点に組ぷよが届くこと
        double v = chain_value(t.chains, t.score) - opt_.w_need * t.need;
        if (opt_.w_waste > 0) v -= opt_.w_waste * std::max(0, t.erased - 4 * t.chains);
        if (opt_.w_junk > 0) v -= opt_.w_junk * t.remain;
        if (!any || v > best) best = v;
        any = true;
    });
    return best;
}

double Evaluator::eval(const Field& field) const {
    double v = opt_.w_base == 0 ? 0.0 : opt_.w_base * (trigger_value(field) + shape(field));
    if (opt_.w_nn > 0) v += opt_.w_nn * global_nn().eval(field);
    if (opt_.w_dual > 0) v += opt_.w_dual * dual_ojama(field);
    if (opt_.max_puyos > 0) v -= opt_.w_over * std::max(0, field.count() - opt_.max_puyos);
    return v;
}

int Evaluator::dual_ojama(const Field& field) const {
    // 発火点を集める（起爆点に届くもの）
    struct T {
        int x;
        Color color;
        int need, chains, score;
    };
    T ts[32];
    int n = 0, main_chains = 0;
    double main_value = 0;
    for_each_trigger(field, [&](const Trigger& t) {
        if (n >= 32 || !field.is_reachable(Move{static_cast<int8_t>(t.x), 0})) return;
        ts[n++] = {t.x, t.color, t.need, t.chains, t.score};
        main_chains = std::max(main_chains, t.chains);
        main_value = std::max(main_value, chain_value(t.chains, t.score));
    });
    if (main_chains < 5) return 0;
    int best = 0;
    for (int i = 0; i < n; ++i) {
        const T& t = ts[i];
        // 対応用はすぐ撃てること（足りないぷよ 2 個まで）
        if (t.chains < opt_.dual_min_chain || t.chains > opt_.dual_max_chain || t.need > 2) continue;
        int oj = std::min(t.score / 70, opt_.dual_cap);
        if (oj <= best) continue;
        // 小連鎖を撃った後の盤面で本線が残るか
        Field f = field;
        for (int k = 0; k < t.need; ++k) f.drop(t.x, t.color);
        f.resolve_chain();
        double after = 0;
        for_each_trigger(f, [&](const Trigger& u) {
            if (u.chains >= 5 && f.is_reachable(Move{static_cast<int8_t>(u.x), 0}))
                after = std::max(after, chain_value(u.chains, u.score));
        });
        if (after >= opt_.dual_keep * main_value) best = oj;
    }
    return best;
}

double Evaluator::shape(const Field& field) const {
    double score = 0.0;
    for (Color c : NORMAL_COLORS) {
        Bits rest = field.plane(c) & VISIBLE;
        rest = rest.andnot(rest.andnot(rest.neighbors()));  // 孤立したぷよは除く
        while (!rest.empty()) {
            Bits g = rest.lowest().expand(rest);
            score += g.popcount() == 2 ? opt_.conn2 : opt_.conn3;
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

}  // namespace puyo
