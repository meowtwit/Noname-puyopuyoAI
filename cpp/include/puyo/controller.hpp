// 操作列生成（Python の puyo/controller.py と同じ仕様）。
//
// 組ぷよの状態は軸ぷよの位置 (x, y) と子ぷよの向き r。出現は軸 (3, 12)・r=0。移動中は 14 段目まで入れる。
// キー: L/R（左右）、A/B（右/左回転。壁蹴り・床蹴りあり）、Q（クイックターン）。最後に真下へ落とす。
// 14 段目に残っているぷよのマスは通れない。盤面の形（高さと 14 段目）だけで決まるので、それをキーに結果を使い回す。
#pragma once

#include <array>
#include <cstdint>
#include <string>
#include <vector>

#include "field.hpp"

namespace puyo {

struct Operation {
    Move move;
    std::string keys;
    int frames;
};

// 操作に関係する盤面の形: 各列の高さ（1〜13 段目）と、14 段目に残っているぷよ
struct Shape {
    std::array<int, WIDTH> h{};
    uint8_t top = 0;  // bit (x-1): x 列目の 14 段目が埋まっている
};

Shape shape_of(const Field& f);
// 置ける場所ごとの最短の操作（all_moves() の順、置けない場所は含まない）
std::vector<Operation> plan_operations(const Shape& s);
// 置ける場所のビット集合（bit i = all_moves()[i]）
uint32_t reachable_mask(const Shape& s);
uint32_t reachable_mask(const Field& f);
// all_moves() での添字（無効な手なら -1）
int move_index(Move m);

}  // namespace puyo
