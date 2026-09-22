// Python から使うための pybind11 モジュール（puyo/_puyocpp.*）。
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <optional>

#include "puyo/beam.hpp"
#include "puyo/detect.hpp"
#include "puyo/lookahead.hpp"
#include "puyo/mcts.hpp"

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
}
