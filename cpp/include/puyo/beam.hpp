// 見えないツモの期待値を取るビームサーチ。
//
// 1. 見えていない先のツモを samples 通り推測する（TsumoSampler）
// 2. それぞれのツモ列で、幅 width・深さ depth のビームサーチを行う
//    - 連鎖が起きたらそこで打ち切り、その連鎖の値（BeamValue::fired）を記録
//    - 起きなければ評価関数 eval（連鎖検出＋形）で順位を付けて上位 width 個を残し、BeamValue::leaf を記録
//    - 初手ごとに、子孫が到達した最大の値を記録
// 3. 初手ごとの値をツモ列全体で平均し、期待値が最大の手を選ぶ
// 値の付け方（BeamValue）を差し替えると、とこぷよ用（大連鎖を組む）と対戦の打ち返し用で同じ探索を使える。
#pragma once

#include <array>
#include <map>
#include <string>
#include <vector>

#include "eval.hpp"
#include "sampler.hpp"

namespace puyo {

struct BeamOptions {
    int width = 40;
    int depth = 10;
    int samples = 8;
    int fire = 10;
    double small_fire = 1.0;  // 目標未満の連鎖を撃ったときの値の割引（残り手数が少ないときは割引しない）
    EvalOptions eval;

    // ビームサーチのオプションなら設定して true
    bool set(const std::string& key, double value);
    static BeamOptions from_map(const std::map<std::string, double>& m);
};

// 探索で付ける値
struct BeamValue {
    virtual ~BeamValue() = default;
    virtual double fired(int chains, int score, const Field& after) const = 0;  // 連鎖を撃った（after: 連鎖後）
    virtual double leaf(double eval, bool last) const = 0;       // 撃っていない（last: 探索の最終手）
};

constexpr double BEAM_NONE = -1e9;  // その初手からは何も得られない（全滅など）

class BeamAI {
public:
    BeamAI(BeamOptions opt, uint64_t seed) : opt_(opt), ev_(opt.eval), sampler_(seed) {}

    // とこぷよ用: fire 連鎖以上を撃つことを目標に組む
    Move decide(const Field& field, const std::vector<Pair>& known, int hands_left,
                const std::array<int, 4>* remaining);

    // 推測したツモを n 手分返す（一様）
    std::vector<Pair> sample_pairs(int n) { return sampler_.extend({}, n, nullptr); }

    // 値の付け方を指定して、初手（legal の順）ごとの期待値（推測したツモ列での平均）を返す
    std::vector<double> expected_values(const Field& field, const std::vector<Move>& legal,
                                        const std::vector<Pair>& known, int depth,
                                        const std::array<int, 4>* remaining, const BeamValue& value);

    const BeamOptions& options() const { return opt_; }
    const Evaluator& evaluator() const { return ev_; }

private:
    void search(const Field& root, const std::vector<Move>& legal, const std::vector<Pair>& seq,
                const BeamValue& value, std::vector<double>& best) const;

    BeamOptions opt_;
    Evaluator ev_;
    TsumoSampler sampler_;
};

}  // namespace puyo
