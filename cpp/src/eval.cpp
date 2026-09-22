#include "puyo/eval.hpp"

#include "puyo/detect.hpp"

namespace puyo {

namespace {

// U 字の理想形（平均高さからのずれ）。Python 版と同じ値
constexpr double U_SHAPE[WIDTH] = {2.0, 0.5, -1.0, -1.0, 0.0, 1.5};
const Bits VISIBLE = Bits::rect(1, VISIBLE_HEIGHT);

}  // namespace

bool EvalOptions::set(const std::string& k, double v) {
    if (k == "w_chain") w_chain = v;
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
        if (!any || v > best) best = v;
        any = true;
    });
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
