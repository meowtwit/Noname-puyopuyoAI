#include "puyo/detect.hpp"

namespace puyo {

std::vector<Trigger> detect_triggers(const Field& field, int max_need) {
    std::vector<Trigger> out;
    for_each_trigger(field, [&](const Trigger& t) { out.push_back(t); }, max_need);
    return out;
}

}  // namespace puyo
