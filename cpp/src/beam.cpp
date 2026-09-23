#include "puyo/beam.hpp"

#include <algorithm>
#include <stdexcept>
#include <unordered_set>

namespace puyo {

namespace {

struct Node {
    Field field;
    int first;  // 初手（legal の添字）
    double e;
};

// とこぷよ用の値: fire 連鎖以上を撃てたら特大。残り手数が探索内で尽きるなら撃った連鎖だけを数える
struct TokopuyoValue : BeamValue {
    const BeamOptions& opt;
    const Evaluator& ev;
    bool endgame;
    TokopuyoValue(const BeamOptions& o, const Evaluator& e, bool end) : opt(o), ev(e), endgame(end) {}
    double fired(int chains, int score, const Field&) const override {
        if (chains >= opt.fire) return 1e7 + score;
        return (endgame ? 1.0 : opt.small_fire) * ev.chain_value(chains, score);
    }
    double leaf(double e, bool, const Field&) const override { return endgame ? -1e6 + e * 1e-3 : e; }
};

}  // namespace

bool BeamOptions::set(const std::string& k, double v) {
    if (k == "width") width = static_cast<int>(v);
    else if (k == "depth") depth = static_cast<int>(v);
    else if (k == "samples") samples = static_cast<int>(v);
    else if (k == "fire") fire = static_cast<int>(v);
    else if (k == "small_fire") small_fire = v;
    else return eval.set(k, v);
    return true;
}

BeamOptions BeamOptions::from_map(const std::map<std::string, double>& m) {
    BeamOptions o;
    for (const auto& [k, v] : m)
        if (!o.set(k, v)) throw std::invalid_argument("unknown option: " + k);
    if (o.width < 1 || o.depth < 1 || o.samples < 1) throw std::invalid_argument("width/depth/samples must be >= 1");
    return o;
}

Move BeamAI::decide(const Field& field, const std::vector<Pair>& known, int hands_left,
                    const std::array<int, 4>* remaining) {
    std::vector<Move> legal = legal_moves(field, known.at(0));

    // 今撃てば目標に届くなら撃つ
    int best_fire = -1, best_fire_score = -1;
    for (size_t i = 0; i < legal.size(); ++i) {
        SimResult s = simulate(field, known[0], legal[i]);
        if (s.chain.chains >= opt_.fire && s.chain.score > best_fire_score) {
            best_fire = static_cast<int>(i);
            best_fire_score = s.chain.score;
        }
    }
    if (best_fire >= 0) return legal[best_fire];

    int depth = opt_.depth;
    if (hands_left >= 0) depth = std::max(1, std::min(depth, hands_left));
    const bool endgame = hands_left >= 0 && hands_left <= opt_.depth;
    std::vector<double> total =
        expected_values(field, legal, known, depth, remaining, TokopuyoValue(opt_, ev_, endgame));
    size_t arg = 0;
    for (size_t i = 1; i < legal.size(); ++i)
        if (total[i] > total[arg]) arg = i;
    return legal.at(arg);
}

std::vector<double> BeamAI::expected_values(const Field& field, const std::vector<Move>& legal,
                                            const std::vector<Pair>& known, int depth,
                                            const std::array<int, 4>* remaining, const BeamValue& value) {
    // 見えているツモだけで探索しきれるなら推測は 1 回で十分
    const int samples = static_cast<int>(known.size()) >= depth ? 1 : opt_.samples;
    std::vector<double> total(legal.size(), 0.0), best;
    for (int s = 0; s < samples; ++s) {
        std::vector<Pair> seq = sampler_.extend(known, depth, remaining);
        best.assign(legal.size(), BEAM_NONE);
        search(field, legal, seq, value, best);
        for (size_t i = 0; i < legal.size(); ++i) total[i] += best[i];
    }
    for (double& t : total) t /= samples;
    return total;
}

void BeamAI::search(const Field& root, const std::vector<Move>& legal, const std::vector<Pair>& seq,
                    const BeamValue& value, std::vector<double>& best) const {
    std::vector<Node> beam{{root, -1, 0.0}}, children;
    std::unordered_set<uint64_t> seen;
    const int depth = static_cast<int>(seq.size());
    for (int d = 0; d < depth; ++d) {
        const bool last = d == depth - 1;
        children.clear();
        for (const Node& node : beam) {
            const std::vector<Move>& moves = d == 0 ? legal : legal_moves(node.field, seq[d]);
            for (size_t i = 0; i < moves.size(); ++i) {
                SimResult s = simulate(node.field, seq[d], moves[i]);
                if (s.field.is_dead()) continue;
                int first = d == 0 ? static_cast<int>(i) : node.first;
                if (s.chain.chains) {  // 撃ったらそこで打ち切り
                    best[first] = std::max(best[first], value.fired(s.chain.chains, s.chain.score, s.field));
                    continue;
                }
                double e = ev_.eval(s.field);
                best[first] = std::max(best[first], value.leaf(e, last, s.field));
                children.push_back({s.field, first, e});
            }
        }
        if (children.empty()) break;
        std::sort(children.begin(), children.end(), [](const Node& a, const Node& b) { return a.e > b.e; });
        beam.clear();
        seen.clear();
        for (const Node& c : children) {
            if (!seen.insert(c.field.hash() ^ (uint64_t(c.first) * 0x9E3779B97F4A7C15ull)).second) continue;
            beam.push_back(c);
            if (static_cast<int>(beam.size()) >= opt_.width) break;
        }
    }
}

}  // namespace puyo
