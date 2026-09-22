// C++ 単体のセルフテスト＆ベンチマーク（Python 不要）。
//
//   selftest <fixtures.txt>
//
// fixtures は Python 版で作った正解（scripts/gen_fixtures.py）。空の列は "-" で表す。
//   S <列×6> <組ぷよ> <x> <rot> <連鎖後の列×6> <連鎖数> <得点> <ちぎり>   … simulate
//   D <列×6> <件数> (<x> <色> <足した数> <連鎖数> <得点>)*               … detect（x, 色, 個数 順）
//   L <列×6> <組ぷよ数> <組ぷよ>* <残り手数> <x> <rot>                   … LookaheadAI.decide
// Windows の AVX2 ビルドでも同じ fixtures が通れば、Python 版と同じ動きをしていると確認できる。
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <sstream>
#include <tuple>

#include "puyo/detect.hpp"
#include "puyo/lookahead.hpp"

using namespace puyo;

namespace {

std::vector<std::string> read_cols(std::istream& in) {
    std::vector<std::string> cols(WIDTH);
    for (auto& c : cols) {
        in >> c;
        if (c == "-") c.clear();
    }
    return cols;
}

std::string join(const std::vector<std::string>& cols) {
    std::string s;
    for (const auto& c : cols) s += (c.empty() ? "-" : c) + " ";
    return s;
}

struct Case {
    Field field;
    std::vector<Pair> pairs;
    int hands_left;
};

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        std::fprintf(stderr, "usage: %s fixtures.txt\n", argv[0]);
        return 2;
    }
    std::ifstream file(argv[1]);
    if (!file) {
        std::fprintf(stderr, "cannot open %s\n", argv[1]);
        return 2;
    }
    std::printf("backend: %s\n", backend_name());

    int n_sim = 0, n_det = 0, n_ai = 0, fails = 0;
    std::vector<std::tuple<Field, Pair, Move>> sims;
    std::vector<Case> cases;
    LookaheadAI ai;
    std::string line;
    while (std::getline(file, line)) {
        std::istringstream in(line);
        std::string kind;
        in >> kind;
        if (kind == "S") {
            auto cols = read_cols(in);
            std::string pair;
            int x, rot, chains, score, tear;
            in >> pair >> x >> rot;
            auto expect = read_cols(in);
            in >> chains >> score >> tear;
            Field f = Field::from_cols(cols);
            Move m{static_cast<int8_t>(x), static_cast<int8_t>(rot)};
            SimResult r = simulate(f, Pair::parse(pair), m);
            ++n_sim;
            sims.emplace_back(f, Pair::parse(pair), m);
            if (r.field.to_cols() != expect || r.chain.chains != chains || r.chain.score != score || r.tear != tear) {
                if (++fails <= 5)
                    std::printf("FAIL S %s%s %d%d: got %s%d %d %d\n", join(cols).c_str(), pair.c_str(), x, rot,
                                join(r.field.to_cols()).c_str(), r.chain.chains, r.chain.score, r.tear);
            }
        } else if (kind == "D") {
            auto cols = read_cols(in);
            int n;
            in >> n;
            std::vector<std::tuple<int, char, int, int, int>> expect(n), got;
            for (auto& [x, c, need, ch, sc] : expect) in >> x >> c >> need >> ch >> sc;
            for (const Trigger& t : detect_triggers(Field::from_cols(cols)))
                got.emplace_back(t.x, color_to_char(t.color), t.need, t.chains, t.score);
            std::sort(got.begin(), got.end());
            ++n_det;
            if (got != expect && ++fails <= 5) std::printf("FAIL D %s\n", join(cols).c_str());
        } else if (kind == "L") {
            auto cols = read_cols(in);
            int np, hands_left, x, rot;
            in >> np;
            std::vector<Pair> pairs;
            for (int i = 0; i < np; ++i) {
                std::string p;
                in >> p;
                pairs.push_back(Pair::parse(p));
            }
            in >> hands_left >> x >> rot;
            Field f = Field::from_cols(cols);
            Move mv = ai.decide(f, pairs, hands_left);
            ++n_ai;
            cases.push_back({f, pairs, hands_left});
            if ((mv.x != x || mv.rot != rot) && ++fails <= 5)
                std::printf("FAIL L %s: expected %d%d got %d%d\n", join(cols).c_str(), x, rot, mv.x, mv.rot);
        }
    }
    std::printf("simulate %d / detect %d / lookahead %d cases: %s (%d failures)\n", n_sim, n_det, n_ai,
                fails ? "NG" : "OK", fails);

    // --- ベンチマーク ---
    using clock = std::chrono::steady_clock;
    if (!sims.empty()) {
        long long sink = 0;
        int reps = std::max<int>(1, 2'000'000 / static_cast<int>(sims.size()));
        auto t0 = clock::now();
        for (int r = 0; r < reps; ++r)
            for (auto& [f, p, m] : sims) sink += simulate(f, p, m).chain.score;
        double ns = std::chrono::duration<double, std::nano>(clock::now() - t0).count() / (double(reps) * sims.size());
        std::printf("simulate: %.1f ns/call (sink %lld)\n", ns, sink % 7);
    }
    if (!cases.empty()) {
        int sink = 0;
        auto t0 = clock::now();
        for (auto& c : cases) sink += ai.decide(c.field, c.pairs, c.hands_left).x;
        double ms = std::chrono::duration<double, std::milli>(clock::now() - t0).count() / cases.size();
        std::printf("lookahead decide: %.2f ms/move (sink %d)\n", ms, sink % 7);
    }
    return fails ? 1 : 0;
}
