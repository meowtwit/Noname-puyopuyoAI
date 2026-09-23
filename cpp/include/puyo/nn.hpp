// 盤面評価ネットワーク（scripts/train_nn.py で学習した全結合ネットワーク）の推論。
//
// 入力: 各マス（6 列 × 14 段）× 色（R, G, B, Y, おじゃま）の 0/1。出力: その盤面から撃てそうな連鎖数。
// 1 層目は置かれているマスの重みの行を足すだけで計算する（入力の大半が 0 のため）。
// プロセス全体で 1 つのモデルを共有する（load_nn で読み込み、評価関数の w_nn > 0 で使う）。
#pragma once

#include <string>
#include <vector>

#include "field.hpp"

namespace puyo {

class Mlp {
public:
    bool load(const std::string& path);
    bool loaded() const { return !layers_.empty(); }
    float eval(const Field& field) const;
    const std::string& path() const { return path_; }

private:
    struct Layer {
        int in = 0, out = 0;
        std::vector<float> w;  // [in][out]
        std::vector<float> b;
    };
    std::vector<Layer> layers_;
    std::string path_;
};

Mlp& global_nn();

}  // namespace puyo
