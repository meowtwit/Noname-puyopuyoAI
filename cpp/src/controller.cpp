#include "puyo/controller.hpp"

#include <queue>
#include <tuple>

namespace puyo {

namespace {

constexpr int MAX_ROW = 14;
constexpr int DX[4] = {0, 1, 0, -1};
constexpr int DY[4] = {1, 0, -1, 0};
constexpr int KEY_FRAMES = 2, QUICK_TURN_FRAMES = 4, DROP_FRAMES_PER_ROW = 2, LOCK_FRAMES = 20, TEAR_FRAMES = 20;
constexpr int N_STATES = WIDTH * MAX_ROW * 4;

struct State {
    int x, y, r;
};
int id(const State& s) { return ((s.x - 1) * MAX_ROW + (s.y - 1)) * 4 + s.r; }
State from_id(int i) { return {i / (MAX_ROW * 4) + 1, (i / 4) % MAX_ROW + 1, i % 4}; }

struct Ctl {
    const std::array<int, WIDTH>& h;
    uint8_t top;
    bool free(int x, int y) const {
        if (x < 1 || x > WIDTH || y < 1 || y > MAX_ROW || y <= h[x - 1]) return false;
        return !(y == MAX_ROW && ((top >> (x - 1)) & 1));
    }
    bool valid(int x, int y, int r) const { return free(x, y) && free(x + DX[r], y + DY[r]); }
    bool rotate(const State& s, int d, State& out) const {
        int r2 = (s.r + d + 4) % 4;
        if (valid(s.x, s.y, r2)) return out = {s.x, s.y, r2}, true;
        if (r2 == 1 || r2 == 3) {  // 壁蹴り
            int x2 = s.x - DX[r2];
            if (valid(x2, s.y, r2)) return out = {x2, s.y, r2}, true;
        } else if (r2 == 2) {  // 床蹴り
            if (valid(s.x, s.y + 1, r2)) return out = {s.x, s.y + 1, r2}, true;
        }
        return false;
    }
    bool quick_turn(const State& s, State& out) const {
        State tmp;
        if ((s.r != 0 && s.r != 2) || rotate(s, 1, tmp) || rotate(s, -1, tmp)) return false;
        int r2 = (s.r + 2) % 4;
        if (valid(s.x, s.y, r2)) return out = {s.x, s.y, r2}, true;
        if (r2 == 2 && valid(s.x, s.y + 1, r2)) return out = {s.x, s.y + 1, r2}, true;
        return false;
    }
    // (キー, フレーム, 行き先) を順に返す（Python と同じ順）
    template <class F>
    void neighbors(const State& s, F&& fn) const {
        State t;
        if (valid(s.x - 1, s.y, s.r)) fn('L', KEY_FRAMES, State{s.x - 1, s.y, s.r});
        if (valid(s.x + 1, s.y, s.r)) fn('R', KEY_FRAMES, State{s.x + 1, s.y, s.r});
        if (rotate(s, 1, t)) fn('A', KEY_FRAMES, t);
        if (rotate(s, -1, t)) fn('B', KEY_FRAMES, t);
        if (quick_turn(s, t)) fn('Q', QUICK_TURN_FRAMES, t);
    }
    int drop_frames(const State& s) const {
        int cx = s.x + DX[s.r];
        if (cx == s.x) {
            int low = std::min(s.y, s.y + DY[s.r]);
            return (low - (h[s.x - 1] + 1)) * DROP_FRAMES_PER_ROW + LOCK_FRAMES;
        }
        int ha = h[s.x - 1], hc = h[cx - 1];
        int fall = s.y - (std::max(ha, hc) + 1);
        int tear = ha > hc ? ha - hc : hc - ha;
        int extra = tear ? TEAR_FRAMES + 10 + 6 * (tear - 1) : 0;
        return fall * DROP_FRAMES_PER_ROW + LOCK_FRAMES + extra;
    }
};

const State SPAWN{3, 12, 0};

}  // namespace

Shape shape_of(const Field& f) {
    Shape s;
    for (int x = 1; x <= WIDTH; ++x) {
        s.h[x - 1] = f.height(x);
        if (f.top(x)) s.top |= static_cast<uint8_t>(1u << (x - 1));
    }
    return s;
}

int move_index(Move m) {
    static const auto table = [] {
        std::array<std::array<int, 4>, WIDTH + 2> t{};
        for (auto& row : t) row.fill(-1);
        const auto& all = all_moves();
        for (size_t i = 0; i < all.size(); ++i) t[all[i].x][all[i].rot] = static_cast<int>(i);
        return t;
    }();
    if (m.x < 1 || m.x > WIDTH || m.rot < 0 || m.rot > 3) return -1;
    return table[m.x][m.rot];
}

std::vector<Operation> plan_operations(const Shape& shape) {
    Ctl c{shape.h, shape.top};
    std::vector<Operation> out;
    if (!c.valid(SPAWN.x, SPAWN.y, SPAWN.r)) return out;
    std::vector<int> dist(N_STATES, 1 << 30);
    std::vector<std::string> keys(N_STATES);
    using Item = std::pair<int, int>;
    std::priority_queue<Item, std::vector<Item>, std::greater<Item>> pq;
    dist[id(SPAWN)] = 0;
    pq.emplace(0, id(SPAWN));
    while (!pq.empty()) {
        auto [d, si] = pq.top();
        pq.pop();
        if (d > dist[si]) continue;
        State s = from_id(si);
        c.neighbors(s, [&](char key, int cost, const State& t) {
            int ti = id(t), nd = d + cost;
            std::string cand = keys[si] + key;
            if (nd < dist[ti] || (nd == dist[ti] && cand < keys[ti])) {
                dist[ti] = nd;
                keys[ti] = std::move(cand);
                pq.emplace(nd, ti);
            }
        });
    }
    const auto& all = all_moves();
    std::vector<int> best_frames(all.size(), -1);
    std::vector<std::string> best_keys(all.size());
    for (int i = 0; i < N_STATES; ++i) {
        if (dist[i] >= (1 << 30)) continue;
        State s = from_id(i);
        int mi = move_index(Move{static_cast<int8_t>(s.x), static_cast<int8_t>(s.r)});
        if (mi < 0) continue;
        int total = dist[i] + c.drop_frames(s);
        if (best_frames[mi] < 0 || std::tie(total, keys[i]) < std::tie(best_frames[mi], best_keys[mi])) {
            best_frames[mi] = total;
            best_keys[mi] = keys[i];
        }
    }
    for (size_t i = 0; i < all.size(); ++i)
        if (best_frames[i] >= 0) out.push_back({all[i], best_keys[i], best_frames[i]});
    return out;
}

uint32_t reachable_mask(const Shape& shape) {
    constexpr uint32_t ALL = (1u << 22) - 1;
    int hmax = 0;
    for (int v : shape.h) hmax = std::max(hmax, v);
    if (hmax <= 11) return ALL;  // 12 段以上の列が無ければどこでも置ける

    // 列の高さ（0..13、4bit × 6）と 14 段目（6bit）をキーにした直接マップのキャッシュ
    uint32_t key = shape.top;
    for (int v : shape.h) key = (key << 4) | static_cast<uint32_t>(v);
    struct Entry {
        uint32_t key = ~0u, mask = 0;
    };
    thread_local std::array<Entry, 4096> cache;
    Entry& e = cache[(key * 2654435761u) >> 20];
    if (e.key == key) return e.mask;

    Ctl c{shape.h, shape.top};
    uint32_t mask = 0;
    if (c.valid(SPAWN.x, SPAWN.y, SPAWN.r)) {
        std::array<bool, N_STATES> seen{};
        std::vector<State> stack{SPAWN};
        seen[id(SPAWN)] = true;
        while (!stack.empty()) {
            State s = stack.back();
            stack.pop_back();
            int mi = move_index(Move{static_cast<int8_t>(s.x), static_cast<int8_t>(s.r)});
            if (mi >= 0) mask |= 1u << mi;
            c.neighbors(s, [&](char, int, const State& t) {
                if (!seen[id(t)]) {
                    seen[id(t)] = true;
                    stack.push_back(t);
                }
            });
        }
    }
    e = {key, mask};
    return mask;
}

uint32_t reachable_mask(const Field& f) { return reachable_mask(shape_of(f)); }

}  // namespace puyo
