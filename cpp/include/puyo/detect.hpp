// 連鎖の検出（Python の puyo/detect.py と同じ。書籍 3.4 RensaDetector の detectByDropStrategy 相当）。
#pragma once

#include <algorithm>
#include <vector>

#include "field.hpp"

namespace puyo {

struct Trigger {
    int x;
    Color color;
    int need;  // 足したぷよの数
    int chains;
    int score;
};

// 各列の上に、周囲にある色のぷよを 1〜max_need 個足して起こせる連鎖を列挙する
std::vector<Trigger> detect_triggers(const Field& field, int max_need = 3);

// 列挙せずにコールバックで受け取る版（探索用）
template <class F>
void for_each_trigger(const Field& field, F&& fn, int max_need = 3) {
    for (int x = 1; x <= WIDTH; ++x) {
        int h = field.height(x);
        if (h >= VISIBLE_HEIGHT) continue;
        // 足したぷよが接しうる位置の色だけ試す
        bool seen[8] = {};
        if (h) seen[field.get(x, h)] = true;
        for (int nx : {x - 1, x + 1}) {
            if (nx < 1 || nx > WIDTH) continue;
            int nh = field.height(nx);
            int top = std::min(h + max_need, VISIBLE_HEIGHT);
            for (int y = h + 1; y <= top && y <= nh; ++y) seen[field.get(nx, y)] = true;
        }
        for (Color color : NORMAL_COLORS) {
            if (!seen[color]) continue;
            Field f = field;
            for (int k = 1; k <= max_need; ++k) {
                if (h + k > VISIBLE_HEIGHT) break;
                f.drop(x, color);
                if (f.connects4(x, h + k)) {
                    ChainResult res = f.resolve_chain();
                    fn(Trigger{x, color, k, res.chains, res.score});
                    break;
                }
            }
        }
    }
}

}  // namespace puyo
