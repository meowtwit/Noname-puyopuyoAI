// 見えていないツモの推測。
//
// AC 通のツモは 128 手（256 個）で 4 色が 64 個ずつ出る。今の周期で残っている色の個数を渡すと、
// そこから非復元抽出で引く（色の偏りを読める）。渡さなければ各色 1/4 の独立な抽選。
#pragma once

#include <array>
#include <cstdint>
#include <random>
#include <vector>

#include "field.hpp"

namespace puyo {

class TsumoSampler {
public:
    explicit TsumoSampler(uint64_t seed) : rng_(seed) {}

    // known の後ろに推測したツモを足して、長さ total の列を作る。
    // remaining: 今の周期で残っている R, G, B, Y の個数（known に含まれる分は引いた後）。nullptr なら一様
    std::vector<Pair> extend(const std::vector<Pair>& known, int total, const std::array<int, 4>* remaining) {
        std::vector<Pair> seq(known.begin(), known.end());
        if (static_cast<int>(seq.size()) >= total) {
            seq.resize(total);
            return seq;
        }
        std::array<int, 4> pool = remaining ? *remaining : std::array<int, 4>{0, 0, 0, 0};
        auto draw = [&]() -> Color {
            if (!remaining) return NORMAL_COLORS[rng_() % 4];
            int sum = pool[0] + pool[1] + pool[2] + pool[3];
            if (sum <= 0) {
                pool = {64, 64, 64, 64};  // 次の周期
                sum = 256;
            }
            int r = static_cast<int>(rng_() % static_cast<uint64_t>(sum));
            for (int i = 0; i < 4; ++i) {
                if (r < pool[i]) {
                    --pool[i];
                    return NORMAL_COLORS[i];
                }
                r -= pool[i];
            }
            return NORMAL_COLORS[3];
        };
        while (static_cast<int>(seq.size()) < total) {
            Color a = draw();
            Color b = draw();
            seq.push_back({a, b});
        }
        return seq;
    }

    std::mt19937_64& rng() { return rng_; }

private:
    std::mt19937_64 rng_;
};

}  // namespace puyo
