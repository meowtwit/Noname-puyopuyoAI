#include "puyo/nn.hpp"

#include <algorithm>
#include <cstring>
#include <fstream>

namespace puyo {

namespace {

// 学習側の色の並び（R, G, B, Y, おじゃま）での添字
int color_index(Color c) {
    switch (c) {
        case RED: return 0;
        case GREEN: return 1;
        case BLUE: return 2;
        case YELLOW: return 3;
        case OJAMA: return 4;
        default: return -1;
    }
}

}  // namespace

bool Mlp::load(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) return false;
    char magic[4];
    int32_t n = 0;
    f.read(magic, 4);
    f.read(reinterpret_cast<char*>(&n), 4);
    if (!f || std::memcmp(magic, "PNN1", 4) != 0 || n <= 0 || n > 16) return false;
    std::vector<Layer> layers(n);
    for (Layer& l : layers) {
        int32_t in = 0, out = 0;
        f.read(reinterpret_cast<char*>(&in), 4);
        f.read(reinterpret_cast<char*>(&out), 4);
        if (!f || in <= 0 || out <= 0) return false;
        l.in = in;
        l.out = out;
        l.w.resize(static_cast<size_t>(in) * out);
        l.b.resize(out);
        f.read(reinterpret_cast<char*>(l.w.data()), static_cast<std::streamsize>(l.w.size() * 4));
        f.read(reinterpret_cast<char*>(l.b.data()), static_cast<std::streamsize>(l.b.size() * 4));
        if (!f) return false;
    }
    if (layers.front().in != WIDTH * TOP_ROW * 5 || layers.back().out != 1) return false;
    layers_ = std::move(layers);
    path_ = path;
    return true;
}

float Mlp::eval(const Field& field) const {
    if (layers_.empty()) return 0.0f;
    const Layer& first = layers_.front();
    float buf_a[512], buf_b[512];
    float* h = buf_a;
    std::copy(first.b.begin(), first.b.end(), h);
    // 1 層目: 置かれているマスの重みの行を足す
    for (int x = 1; x <= WIDTH; ++x) {
        const int hgt = field.height(x);
        for (int y = 1; y <= TOP_ROW; ++y) {
            if (y > hgt && !(y == TOP_ROW && field.top(x))) continue;
            const int ci = color_index(field.get(x, y));
            if (ci < 0) continue;
            const float* row = &first.w[static_cast<size_t>(((x - 1) * TOP_ROW + (y - 1)) * 5 + ci) * first.out];
            for (int j = 0; j < first.out; ++j) h[j] += row[j];
        }
    }
    int width = first.out;
    for (size_t li = 1; li < layers_.size(); ++li) {
        for (int j = 0; j < width; ++j) h[j] = std::max(h[j], 0.0f);  // ReLU
        const Layer& l = layers_[li];
        float* o = h == buf_a ? buf_b : buf_a;
        std::copy(l.b.begin(), l.b.end(), o);
        for (int i = 0; i < l.in; ++i) {
            const float hi = h[i];
            if (hi == 0.0f) continue;
            const float* row = &l.w[static_cast<size_t>(i) * l.out];
            for (int j = 0; j < l.out; ++j) o[j] += hi * row[j];
        }
        h = o;
        width = l.out;
    }
    return h[0];
}

Mlp& global_nn() {
    static Mlp nn;
    return nn;
}

}  // namespace puyo
