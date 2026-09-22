// 見えないツモの期待値を取るビームサーチ。
//
// 1. 見えていない先のツモを samples 通り推測する（TsumoSampler）
// 2. それぞれのツモ列で、幅 width・深さ depth のビームサーチを行う
//    - 連鎖が起きたらそこで打ち切り、その連鎖の評価（fire 連鎖以上なら特大）を記録
//    - 起きなければ評価関数 eval（連鎖検出＋形）で順位を付けて上位 width 個を残す
//    - 初手ごとに、子孫が到達した最大の評価を記録
// 3. 初手ごとの評価をツモ列全体で平均し、期待値が最大の手を選ぶ
// 残り手数が探索の深さ以内なら「撃った連鎖」だけを評価する（撃たずに終わると 0 点のため）。
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

    static BeamOptions from_map(const std::map<std::string, double>& m);
};

class BeamAI {
public:
    BeamAI(BeamOptions opt, uint64_t seed) : opt_(opt), ev_(opt.eval), sampler_(seed) {}

    Move decide(const Field& field, const std::vector<Pair>& known, int hands_left,
                const std::array<int, 4>* remaining);

private:
    // 1 つのツモ列でビームサーチし、初手（legal の添字）ごとの最大評価を best に入れる
    void search(const Field& root, const std::vector<Move>& legal, const std::vector<Pair>& seq, bool endgame,
                std::vector<double>& best) const;
    double fired_value(int chains, int score, bool endgame) const;

    BeamOptions opt_;
    Evaluator ev_;
    TsumoSampler sampler_;
};

}  // namespace puyo
