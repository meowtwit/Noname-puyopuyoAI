// ぷよぷよ通ルールのフィールド（Python の puyo/core.py と同じ仕様をビットボードで実装）。
#pragma once

#include <array>
#include <cstdint>
#include <string>
#include <vector>

#include "bits.hpp"

namespace puyo {

constexpr int WIDTH = 6;
constexpr int HEIGHT = 13;          // 保持する段数
constexpr int VISIBLE_HEIGHT = 12;  // 連鎖判定に参加する段数

// 3 枚のビット面で表す色コード（色ぷよは bit2 が立つ）
enum Color : uint8_t { EMPTY = 0, OJAMA = 1, RED = 4, GREEN = 5, BLUE = 6, YELLOW = 7 };
constexpr std::array<Color, 4> NORMAL_COLORS = {RED, GREEN, BLUE, YELLOW};

inline bool is_normal(Color c) { return c >= RED; }
Color color_from_char(char c);  // R G B Y O .
char color_to_char(Color c);

struct Pair {
    Color axis, child;
    bool is_double() const { return axis == child; }
    static Pair parse(const std::string& s) { return {color_from_char(s.at(0)), color_from_char(s.at(1))}; }
};

// x: 軸ぷよの列 (1..6)、rot: 子ぷよの向き 0=上 1=右 2=下 3=左
struct Move {
    int8_t x = 0, rot = 0;
    int child_x() const { return x + (rot == 1 ? 1 : rot == 3 ? -1 : 0); }
    bool operator==(const Move& o) const { return x == o.x && rot == o.rot; }
};

// Python の ALL_MOVES / moves_for と同じ順序（x 昇順、rot 昇順）
const std::vector<Move>& all_moves();
const std::vector<Move>& double_moves();
inline const std::vector<Move>& moves_for(const Pair& p) { return p.is_double() ? double_moves() : all_moves(); }

struct ChainResult {
    int chains = 0;
    int score = 0;
};

class Field {
public:
    Field() = default;
    // 列ごとの文字列（下から、Python の Field.to_json() と同じ形式）
    static Field from_cols(const std::vector<std::string>& cols);
    std::vector<std::string> to_cols() const;

    Bits occupied() const { return p_[0] | p_[1] | p_[2]; }
    Bits plane(Color c) const;
    Color get(int x, int y) const;
    int height(int x) const { return std::popcount(occupied().lane(x)); }
    int count() const { return occupied().popcount(); }
    bool is_dead() const { return occupied().test(3, 12); }
    bool is_empty() const { return occupied().empty(); }
    bool operator==(const Field& o) const { return p_[0] == o.p_[0] && p_[1] == o.p_[1] && p_[2] == o.p_[2]; }
    uint64_t hash() const {
        uint64_t h = 0x9E3779B97F4A7C15ull;
        for (const Bits& b : p_) {
            h = (h ^ b.lo()) * 0xBF58476D1CE4E5B9ull;
            h = (h ^ b.hi()) * 0x94D049BB133111EBull;
        }
        return h ^ (h >> 31);
    }

    bool is_reachable(Move m) const;
    // 置いて連鎖は起こさない。ちぎり段差を返す
    int place(const Pair& pair, Move m);
    void drop(int x, Color c);  // 1 個落とす（14 段目以上は消滅）
    bool connects4(int x, int y) const;
    ChainResult resolve_chain();

private:
    void remove_and_fall(Bits erase);
    Bits p_[3];
};

// 非破壊で設置→連鎖。Python の simulate() と同じ
struct SimResult {
    Field field;
    ChainResult chain;
    int tear;
};
SimResult simulate(const Field& f, const Pair& pair, Move m);

std::vector<Move> legal_moves(const Field& f, const Pair& pair);

}  // namespace puyo
