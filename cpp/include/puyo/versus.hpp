// 対戦用 AI。
//
// 基本戦略: 自分からは撃たずに組み、相手が発火したら、おじゃまが降るまでに置ける手数（window）の中で打ち返す。
//   1. 今撃てば相手を倒せるなら撃つ。倒せる = 送るおじゃま ≥ 相手の 3 列目を埋める量 ＋ 相手が打ち返せる量 ＋ kill_margin。
//      相手が打ち返せる量は、相手の立場でビームサーチして「自分の連鎖が終わるまでに相手が撃てる最大のおじゃま」を見積もる
//      （fire 連鎖以上でも撃つ。対戦では fire の既定は 99 = 連鎖数だけでは撃たない）
//   2. 来るおじゃまが accept 個を超え、降るまでの手数がビームの深さ以内なら、打ち返し探索:
//      「送り返すおじゃま − 来るおじゃま」が最大になる発火をビームサーチで探す（撃たずに受けるのも候補）
//   3. それ以外はとこぷよと同じく連鎖を組む（盤面が埋まってくると撃つ枝しか残らなくなり、自然に撃つ）
#pragma once

#include <map>
#include <string>
#include <vector>

#include "beam.hpp"

namespace puyo {

constexpr int OJAMA_RATE = 70;  // 70 点でおじゃま 1 個（通）

struct VersusOptions {
    BeamOptions beam = [] {
        BeamOptions b;
        b.fire = 99;
        return b;
    }();
    int accept = 6;          // これ以下のおじゃまは受ける
    double w_ojama = 100;    // 打ち返し探索でのおじゃま 1 個の値
    int counter_need = 3;    // 相手の打ち返し力を見積もるとき、足りないぷよ何個までの連鎖を数えるか
    int kill_margin = 30;    // 倒せると判断するのに上乗せするおじゃま

    static VersusOptions from_map(const std::map<std::string, double>& m);
};

struct VersusContext {
    int incoming = 0;  // 自分に来るおじゃま（相手の連鎖中なら、その連鎖の残りの分も含めた見込み）
    int window = 0;    // おじゃまが降るまでに置ける手数（この手を含む）。来ないなら 0
    int carry = 0;     // 得点の端数（おじゃまに換算していない分）
    std::vector<Pair> opp_pairs;  // 相手がこれから置く組ぷよのうち分かっているもの（共通のツモ列で自分が見た範囲）
    int hand_frames = 40;
    int chain_frames = 60;
};

class VersusAI {
public:
    VersusAI(VersusOptions opt, uint64_t seed) : opt_(opt), beam_(opt.beam, seed) {}

    Move decide(const Field& field, const std::vector<Pair>& known, const std::array<int, 4>* remaining,
                const VersusContext& ctx, const Field& opponent);

    // 相手が今の盤面から打ち返せるおじゃまの見込み（色ぷよを counter_need 個まで足して起こせる最大の連鎖）
    int counter_potential(const Field& opponent) const;
    // 相手が window 手のうちに撃てる最大のおじゃまの見込み（相手の立場でビームサーチ）
    int opponent_counter(const Field& opponent, const std::vector<Pair>& opp_pairs, int window);
    // 相手を倒すのに必要なおじゃま（3 列目を 12 段目まで埋める量）
    static int lethal(const Field& opponent) { return WIDTH * (VISIBLE_HEIGHT - opponent.height(3)); }

private:
    VersusOptions opt_;
    BeamAI beam_;
};

}  // namespace puyo
