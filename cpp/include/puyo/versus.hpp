// 対戦用 AI。
//
// 基本戦略: 自分からは撃たずに組み、相手が発火したら、おじゃまが降るまでに置ける手数（window）の中で打ち返す。
//   1. 今撃てば相手を倒せるなら撃つ。倒せる = 送るおじゃま ≥ 相手の 3 列目を埋める量 ＋ 相手が打ち返せる量 ＋ kill_margin。
//      相手が打ち返せる量は、相手の立場でビームサーチして「自分の連鎖が終わるまでに相手が撃てる最大のおじゃま」を見積もる
//      （fire 連鎖以上でも撃つ。対戦では fire の既定は 99 = 連鎖数だけでは撃たない）
//   2. 来るおじゃまが accept 個を超え、降るまでの手数がビームの深さ以内なら、打ち返し探索:
//      「送り返すおじゃま − 来るおじゃま」が最大になる発火をビームサーチで探す（撃たずに受けるのも候補）
//   3. 潰し: 見えている crush_depth 手の中で、crush_max_chain 連鎖以下・crush_min 個以上のおじゃまを送れる発火があり、
//      相手がそれを打ち返せない（相手の立場でビームサーチして見積もる）なら、最短で撃つ
//   4. それ以外はとこぷよと同じく連鎖を組む（盤面が埋まってくると撃つ枝しか残らなくなり、自然に撃つ）
// 打ち返し・倒しでは、撃った後に残る連鎖の見込み（2 本目）も residual の割合で加点する。
// 相手に返されても、その返しが降るまでに 2 本目を撃って返し返すため。
#pragma once

#include <map>
#include <string>
#include <tuple>
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
    double residual = 0.5;   // 撃った後に残る連鎖（2 本目）のおじゃまの見込みを何割として数えるか
    // 潰しをするか。既定は無効: 打ち返す相手には効かず（届くまでに相手は 5〜6 手置けて小連鎖で返される）、
    // 潰し最速（crush=1 crush_check=0 crush_until=8）は versus 同士で勝率 33%。打ち返さない beam 相手でも差は誤差程度
    int crush = 0;
    int crush_min = 12;      // 潰しとみなす最小のおじゃま（2 段）
    int crush_max_chain = 3; // 潰しに使う連鎖の上限
    int crush_depth = 3;     // 何手先までの潰しを探すか
    // 潰す前に相手が返せる量をどう見積もるか: 0=見ない / 1=相手に見えているツモだけで / 2=先のツモも推測して
    int crush_check = 1;
    int crush_until = 99;    // この手数（0 始まり）までしか潰さない（潰し最速なら小さくする）

    static VersusOptions from_map(const std::map<std::string, double>& m);
};

struct VersusContext {
    int incoming = 0;  // 自分に来るおじゃま（相手の連鎖中なら、その連鎖の残りの分も含めた見込み）
    int window = 0;    // おじゃまが降るまでに置ける手数（この手を含む）。来ないなら 0
    int carry = 0;     // 得点の端数（おじゃまに換算していない分）
    std::vector<Pair> opp_pairs;  // 相手がこれから置く組ぷよのうち分かっているもの（共通のツモ列で自分が見た範囲）
    int hand_frames = 40;
    int chain_frames = 60;
    int hand = 0;  // 自分の手数（0 始まり）
};

class VersusAI {
public:
    VersusAI(VersusOptions opt, uint64_t seed) : opt_(opt), beam_(opt.beam, seed) {}

    Move decide(const Field& field, const std::vector<Pair>& known, const std::array<int, 4>* remaining,
                const VersusContext& ctx, const Field& opponent);

    // 相手が今の盤面から打ち返せるおじゃまの見込み（色ぷよを counter_need 個まで足して起こせる最大の連鎖）
    int counter_potential(const Field& opponent) const;
    // 相手が window 手のうちに撃てる最大のおじゃまの見込み（相手の立場でビームサーチ）
    // visible_only なら推測せず、分かっている組ぷよの範囲だけで探す
    int opponent_counter(const Field& opponent, const std::vector<Pair>& opp_pairs, int window,
                         bool visible_only = false);
    // 相手を倒すのに必要なおじゃま（3 列目を 12 段目まで埋める量）
    static int lethal(const Field& opponent) { return WIDTH * (VISIBLE_HEIGHT - opponent.height(3)); }
    // 潰しの見込み（デバッグ用）: (手の添字, 送れるおじゃまの見込み, 相手が返せる量の見込み)
    std::tuple<int, double, int> crush_plan(const Field& field, const std::vector<Pair>& known,
                                            const std::array<int, 4>* remaining, const VersusContext& ctx,
                                            const Field& opponent);
    // 盤面に残る連鎖（色ぷよを 2 個まで足して起こせる最大の連鎖）のおじゃまの見込み
    static int residual_ojama(const Field& field);

private:
    VersusOptions opt_;
    BeamAI beam_;
};

}  // namespace puyo
