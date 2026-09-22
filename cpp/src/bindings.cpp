// Python から使うための pybind11 モジュール（puyo/_puyocpp.*）。
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <optional>

#include "puyo/beam.hpp"
#include "puyo/detect.hpp"
#include "puyo/lookahead.hpp"
#include "puyo/mcts.hpp"
#include "puyo/versus.hpp"

namespace py = pybind11;
using namespace puyo;

namespace {

std::vector<Pair> parse_pairs(const std::vector<std::string>& ps) {
    std::vector<Pair> out;
    for (const auto& s : ps) out.push_back(Pair::parse(s));
    return out;
}

// 見えないツモを推測する AI（beam / mcts）を Python から呼ぶ
template <class AI, class Options>
void bind_sampling_ai(py::module_& m, const char* name, const char* doc) {
    py::class_<AI>(m, name, doc)
        .def(py::init([](const std::map<std::string, double>& opts, uint64_t seed) {
                 return AI(Options::from_map(opts), seed);
             }),
             py::arg("options") = std::map<std::string, double>{}, py::arg("seed") = 0)
        .def(
            "decide",
            [](AI& ai, const std::vector<std::string>& cols, const std::vector<std::string>& pairs, int hands_left,
               std::optional<std::array<int, 4>> remaining) {
                Field f = Field::from_cols(cols);
                std::vector<Pair> ps = parse_pairs(pairs);
                Move mv;
                {
                    py::gil_scoped_release release;
                    mv = ai.decide(f, ps, hands_left, remaining ? &*remaining : nullptr);
                }
                return py::make_tuple(int(mv.x), int(mv.rot));
            },
            py::arg("cols"), py::arg("pairs"), py::arg("hands_left") = -1, py::arg("remaining") = py::none(),
            "remaining: 今の周期で残っている R, G, B, Y の個数（None なら一様に推測）");
}

}  // namespace

PYBIND11_MODULE(_puyocpp, m) {
    m.doc() = "ぷよぷよ AI のビットボード実装（C++）";
    m.attr("backend") = backend_name();

    m.def(
        "simulate",
        [](const std::vector<std::string>& cols, const std::string& pair, int x, int rot) {
            SimResult r = simulate(Field::from_cols(cols), Pair::parse(pair),
                                   Move{static_cast<int8_t>(x), static_cast<int8_t>(rot)});
            return py::make_tuple(r.field.to_cols(), r.chain.chains, r.chain.score, r.tear);
        },
        py::arg("cols"), py::arg("pair"), py::arg("x"), py::arg("rot"),
        "設置→連鎖。(連鎖後の列, 連鎖数, 得点, ちぎり段差) を返す");

    m.def(
        "resolve_chain",
        [](const std::vector<std::string>& cols) {
            Field f = Field::from_cols(cols);
            ChainResult r = f.resolve_chain();
            return py::make_tuple(f.to_cols(), r.chains, r.score);
        },
        py::arg("cols"));

    m.def(
        "detect",
        [](const std::vector<std::string>& cols) {
            py::list out;
            for (const Trigger& t : detect_triggers(Field::from_cols(cols)))
                out.append(py::make_tuple(t.x, std::string(1, color_to_char(t.color)), t.need, t.chains, t.score));
            return out;
        },
        py::arg("cols"), "(列, 色, 足した数, 連鎖数, 得点) のリスト");

    py::class_<LookaheadAI>(m, "LookaheadAI")
        .def(py::init([](const std::map<std::string, double>& opts) {
                 return LookaheadAI(LookaheadOptions::from_map(opts));
             }),
             py::arg("options") = std::map<std::string, double>{})
        .def(
            "decide",
            [](const LookaheadAI& ai, const std::vector<std::string>& cols, const std::vector<std::string>& pairs,
               int hands_left) {
                Field f = Field::from_cols(cols);
                std::vector<Pair> ps = parse_pairs(pairs);
                Move mv;
                {
                    py::gil_scoped_release release;
                    mv = ai.decide(f, ps, hands_left);
                }
                return py::make_tuple(int(mv.x), int(mv.rot));
            },
            py::arg("cols"), py::arg("pairs"), py::arg("hands_left") = -1,
            "pairs は [手持ち, NEXT1, NEXT2, ...]。hands_left < 0 は無制限。(x, rot) を返す");

    bind_sampling_ai<BeamAI, BeamOptions>(m, "BeamAI", "見えないツモの期待値を取るビームサーチ");
    bind_sampling_ai<MctsAI, MctsOptions>(m, "MctsAI", "見えないツモを推測し直す open-loop MCTS");

    py::class_<VersusAI>(m, "VersusAI", "対戦用 AI（打ち返し）")
        .def(py::init([](const std::map<std::string, double>& opts, uint64_t seed) {
                 return VersusAI(VersusOptions::from_map(opts), seed);
             }),
             py::arg("options") = std::map<std::string, double>{}, py::arg("seed") = 0)
        .def(
            "decide",
            [](VersusAI& ai, const std::vector<std::string>& cols, const std::vector<std::string>& pairs,
               std::optional<std::array<int, 4>> remaining, int incoming, int window, int carry,
               const std::vector<std::string>& opp_cols, const std::vector<std::string>& opp_pairs, int hand_frames,
               int chain_frames, int hand) {
                Field f = Field::from_cols(cols), opp = Field::from_cols(opp_cols);
                std::vector<Pair> ps = parse_pairs(pairs);
                VersusContext ctx{incoming, window, carry, parse_pairs(opp_pairs), hand_frames, chain_frames, hand};
                Move mv;
                {
                    py::gil_scoped_release release;
                    mv = ai.decide(f, ps, remaining ? &*remaining : nullptr, ctx, opp);
                }
                return py::make_tuple(int(mv.x), int(mv.rot));
            },
            py::arg("cols"), py::arg("pairs"), py::arg("remaining"), py::arg("incoming"), py::arg("window"),
            py::arg("carry"), py::arg("opp_cols"), py::arg("opp_pairs") = std::vector<std::string>{},
            py::arg("hand_frames") = 40, py::arg("chain_frames") = 60, py::arg("hand") = 0)
        .def("counter_potential", [](const VersusAI& ai, const std::vector<std::string>& opp_cols) {
            return ai.counter_potential(Field::from_cols(opp_cols));
        })
        .def("crush_plan", [](VersusAI& ai, const std::vector<std::string>& cols, const std::vector<std::string>& pairs,
                              int carry, const std::vector<std::string>& opp_cols,
                              const std::vector<std::string>& opp_pairs) {
            VersusContext ctx{0, 0, carry, parse_pairs(opp_pairs), 40, 60};
            return ai.crush_plan(Field::from_cols(cols), parse_pairs(pairs), nullptr, ctx, Field::from_cols(opp_cols));
        }, "デバッグ用: (手の添字, 潰しで送れるおじゃまの見込み, 相手が返せる量の見込み)");
}
