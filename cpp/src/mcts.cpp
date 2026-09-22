#include "puyo/mcts.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <utility>

namespace puyo {

namespace {

constexpr double DEAD = -5.0;       // 窒息（連鎖数の単位）
constexpr double FIRE_BONUS = 5.0;  // 目標連鎖を撃てたときの上乗せ
constexpr double ENDGAME_POTENTIAL = 0.3;  // 残り手数が少ないとき、撃っていない見込みの割引

}  // namespace

MctsOptions MctsOptions::from_map(const std::map<std::string, double>& m) {
    MctsOptions o;
    for (const auto& [k, v] : m) {
        if (k == "iterations") o.iterations = static_cast<int>(v);
        else if (k == "depth") o.depth = static_cast<int>(v);
        else if (k == "c") o.c = v;
        else if (k == "fire") o.fire = static_cast<int>(v);
        else if (k == "pw_k") o.pw_k = v;
        else if (k == "pw_alpha") o.pw_alpha = v;
        else if (k == "small_fire") o.small_fire = v;
        else if (!o.eval.set(k, v)) throw std::invalid_argument("unknown option: " + k);
    }
    if (o.iterations < 1 || o.depth < 1) throw std::invalid_argument("iterations/depth must be >= 1");
    return o;
}

void MctsAI::legal_indices(const Field& field, const Pair& pair, std::vector<int>& out) {
    out.clear();
    const auto& all = all_moves();
    for (int i = 0; i < N_MOVES; ++i) {
        if (pair.is_double() && all[i].rot >= 2) continue;  // ゾロの下向き・左向きは重複
        if (field.is_reachable(all[i])) out.push_back(i);
    }
}

double MctsAI::value_of(const SimResult& s, bool last, bool endgame) const {
    const double w = ev_.options().w_chain;
    if (s.field.is_dead()) return DEAD;
    if (s.chain.chains) {
        double v = ev_.chain_value(s.chain.chains, s.chain.score) / w;
        if (s.chain.chains >= opt_.fire) return FIRE_BONUS + v;
        return (endgame ? 1.0 : opt_.small_fire) * v;
    }
    if (last && endgame) return 0.0;  // 撃たずにゲームが終わる
    return (endgame ? ENDGAME_POTENTIAL : 1.0) * ev_.eval(s.field) / w;
}

double MctsAI::expand(Node& node, const Field& field, const Pair& pair, bool last, bool endgame) const {
    std::vector<int> idx;
    legal_indices(field, pair, idx);
    double best = DEAD;
    for (int a : idx) {
        node.prior[a] = value_of(simulate(field, pair, all_moves()[a]), last, endgame);
        best = std::max(best, node.prior[a]);
    }
    std::sort(idx.begin(), idx.end(), [&](int a, int b) { return node.prior[a] > node.prior[b]; });
    node.n_order = static_cast<int>(idx.size());
    for (int i = 0; i < node.n_order; ++i) node.order[i] = static_cast<int8_t>(idx[i]);
    node.expanded = true;
    return best;
}

Move MctsAI::decide(const Field& field, const std::vector<Pair>& known, int hands_left,
                    const std::array<int, 4>* remaining) {
    const auto& all = all_moves();
    std::vector<int> root_legal;
    legal_indices(field, known.at(0), root_legal);
    root_visits_.fill(0);

    // 今撃てば目標に届くなら撃つ
    int best_fire = -1, best_fire_score = -1;
    for (int a : root_legal) {
        SimResult s = simulate(field, known[0], all[a]);
        if (s.chain.chains >= opt_.fire && s.chain.score > best_fire_score) {
            best_fire = a;
            best_fire_score = s.chain.score;
        }
    }
    if (best_fire >= 0) return all[best_fire];

    int depth = opt_.depth;
    if (hands_left >= 0) depth = std::max(1, std::min(depth, hands_left));
    const bool endgame = hands_left >= 0 && hands_left <= opt_.depth;

    Node root;
    expand(root, field, known[0], depth == 1, endgame);

    std::vector<int> idx;
    std::vector<std::pair<Node*, int>> path;
    for (int it = 0; it < opt_.iterations; ++it) {
        std::vector<Pair> seq = sampler_.extend(known, depth, remaining);
        Field f = field;
        Node* node = &root;
        double value = DEAD;
        path.clear();
        for (int d = 0; d < depth; ++d) {
            legal_indices(f, seq[d], idx);
            if (idx.empty()) break;  // 置ける場所が無い
            // progressive widening: 事前値の上位 k 手（今のツモで合法なもの）に絞る
            const int k = std::max(1, static_cast<int>(std::ceil(opt_.pw_k * std::pow(node->visits + 1.0, opt_.pw_alpha))));
            std::array<bool, N_MOVES> ok{};
            for (int a : idx) ok[a] = true;
            idx.clear();
            for (int i = 0; i < node->n_order && static_cast<int>(idx.size()) < k; ++i)
                if (ok[node->order[i]]) idx.push_back(node->order[i]);
            if (idx.empty())  // 展開時と組ぷよが違い合法手がずれた
                for (int a = 0; a < N_MOVES && static_cast<int>(idx.size()) < k; ++a)
                    if (ok[a]) idx.push_back(a);
            const double log_n = std::log(node->visits + 1.0);
            int best_a = idx[0];
            double best_u = -1e18;
            for (int a : idx) {
                double q = (node->w[a] + node->prior[a]) / (node->n[a] + 1);
                double u = q + opt_.c * std::sqrt(log_n / (node->n[a] + 1));
                if (u > best_u) {
                    best_u = u;
                    best_a = a;
                }
            }
            path.emplace_back(node, best_a);
            SimResult s = simulate(f, seq[d], all[best_a]);
            const bool last = d == depth - 1;
            if (s.field.is_dead() || s.chain.chains || last) {
                value = value_of(s, last, endgame);
                break;
            }
            f = s.field;
            auto& child = node->child[best_a];
            if (!child) child = std::make_unique<Node>();
            if (!child->expanded) {
                value = expand(*child, f, seq[d + 1], d + 1 == depth - 1, endgame);
                break;
            }
            node = child.get();
        }
        for (auto& [nd, a] : path) {
            nd->visits += 1;
            nd->n[a] += 1;
            nd->w[a] += value;
        }
    }

    int best = root_legal.at(0);
    for (int a : root_legal) {
        root_visits_[a] = root.n[a];
        auto key = [&](int b) { return std::make_pair(root.n[b], (root.w[b] + root.prior[b]) / (root.n[b] + 1)); };
        if (key(a) > key(best)) best = a;
    }
    return all[best];
}

}  // namespace puyo
