#include "puyo/field.hpp"

#include <algorithm>
#include <stdexcept>

namespace puyo {

namespace {

const int CHAIN_BONUS[] = {0, 8, 16, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448, 480, 512};
const int COLOR_BONUS[] = {0, 0, 3, 6, 12, 24};

int chain_bonus(int chain) { return CHAIN_BONUS[(chain < 19 ? chain : 19) - 1]; }
int connection_bonus(int n) {
    if (n <= 4) return 0;
    if (n >= 11) return 10;
    return n - 3;  // 5→2, 6→3, ..., 10→7
}

const Bits VISIBLE = Bits::rect(1, VISIBLE_HEIGHT);

}  // namespace

Color color_from_char(char c) {
    switch (c) {
        case '.': return EMPTY;
        case 'R': case 'r': return RED;
        case 'G': case 'g': return GREEN;
        case 'B': case 'b': return BLUE;
        case 'Y': case 'y': return YELLOW;
        case 'O': case 'o': return OJAMA;
    }
    throw std::invalid_argument(std::string("bad color char: ") + c);
}

char color_to_char(Color c) {
    switch (c) {
        case EMPTY: return '.';
        case OJAMA: return 'O';
        case RED: return 'R';
        case GREEN: return 'G';
        case BLUE: return 'B';
        case YELLOW: return 'Y';
    }
    return '?';
}

const std::vector<Move>& all_moves() {
    static const std::vector<Move> moves = [] {
        std::vector<Move> v;
        for (int x = 1; x <= WIDTH; ++x)
            for (int r = 0; r < 4; ++r) {
                Move m{static_cast<int8_t>(x), static_cast<int8_t>(r)};
                if (m.child_x() >= 1 && m.child_x() <= WIDTH) v.push_back(m);
            }
        return v;
    }();
    return moves;
}

const std::vector<Move>& double_moves() {
    static const std::vector<Move> moves = [] {
        std::vector<Move> v;
        for (Move m : all_moves())
            if (m.rot <= 1) v.push_back(m);
        return v;
    }();
    return moves;
}

Field Field::from_cols(const std::vector<std::string>& cols) {
    if (cols.size() != WIDTH) throw std::invalid_argument("need 6 columns");
    Field f;
    for (int x = 1; x <= WIDTH; ++x) {
        const std::string& s = cols[x - 1];
        if (static_cast<int>(s.size()) > HEIGHT) throw std::invalid_argument("column too tall");
        for (char ch : s) {
            Color c = color_from_char(ch);
            if (c == EMPTY) throw std::invalid_argument("empty inside column");
            f.drop(x, c);
        }
    }
    return f;
}

std::vector<std::string> Field::to_cols() const {
    std::vector<std::string> out(WIDTH);
    for (int x = 1; x <= WIDTH; ++x) {
        int h = height(x);
        for (int y = 1; y <= h; ++y) out[x - 1].push_back(color_to_char(get(x, y)));
    }
    return out;
}

Bits Field::plane(Color c) const {
    Bits r = (c & 1) ? p_[0] : Bits::rect(1, 15).andnot(p_[0]);
    r = r & ((c & 2) ? p_[1] : Bits::rect(1, 15).andnot(p_[1]));
    r = r & ((c & 4) ? p_[2] : Bits::rect(1, 15).andnot(p_[2]));
    return c == EMPTY ? Bits() : r;
}

Color Field::get(int x, int y) const {
    int c = (p_[0].test(x, y) ? 1 : 0) | (p_[1].test(x, y) ? 2 : 0) | (p_[2].test(x, y) ? 4 : 0);
    return static_cast<Color>(c);
}

void Field::drop(int x, Color c) {
    int h = height(x);
    if (h >= HEIGHT) return;
    Bits b = Bits::bit(x, h + 1);
    if (c & 1) p_[0] = p_[0] | b;
    if (c & 2) p_[1] = p_[1] | b;
    if (c & 4) p_[2] = p_[2] | b;
}

bool Field::is_reachable(Move m) const {
    int lo = std::min({3, int(m.x), m.child_x()});
    int hi = std::max({3, int(m.x), m.child_x()});
    for (int x = lo; x <= hi; ++x)
        if (height(x) >= HEIGHT) return false;
    return true;
}

int Field::place(const Pair& pair, Move m) {
    if (m.rot == 2) {
        drop(m.x, pair.child);
        drop(m.x, pair.axis);
        return 0;
    }
    if (m.rot == 0) {
        drop(m.x, pair.axis);
        drop(m.x, pair.child);
        return 0;
    }
    int ha = height(m.x), hc = height(m.child_x());
    drop(m.x, pair.axis);
    drop(m.child_x(), pair.child);
    return ha > hc ? ha - hc : hc - ha;
}

bool Field::connects4(int x, int y) const {
    if (y < 1 || y > VISIBLE_HEIGHT) return false;
    Color c = get(x, y);
    if (!is_normal(c)) return false;
    return Bits::bit(x, y).expand(plane(c) & VISIBLE).popcount() >= 4;
}

void Field::remove_and_fall(Bits erase) {
    uint16_t occ[8], er[8], lanes[3][8];
    occupied().to_lanes(occ);
    erase.to_lanes(er);
    for (int i = 0; i < 3; ++i) p_[i].to_lanes(lanes[i]);
    for (int x = 1; x <= WIDTH; ++x) {
        if (!er[x]) continue;
        uint32_t keep = occ[x] & ~er[x] & 0xFFFE;
        for (int i = 0; i < 3; ++i) lanes[i][x] = static_cast<uint16_t>(pext16(lanes[i][x], keep) << 1);
    }
    for (int i = 0; i < 3; ++i) p_[i] = Bits::from_lanes(lanes[i]);
}

ChainResult Field::resolve_chain() {
    ChainResult result;
    while (true) {
        Bits pr = plane(RED) & VISIBLE, pg = plane(GREEN) & VISIBLE;
        Bits pb = plane(BLUE) & VISIBLE, py = plane(YELLOW) & VISIBLE;
        Bits2 v1 = vanishing(Bits2(pr, pg));
        Bits2 v2 = vanishing(Bits2(pb, py));
        Bits vs[4] = {v1.first(), v1.second(), v2.first(), v2.second()};
        Bits all = vs[0] | vs[1] | vs[2] | vs[3];
        if (all.empty()) return result;

        ++result.chains;
        int colors = 0, n_normal = 0, conn = 0;
        for (Bits v : vs) {
            if (v.empty()) continue;
            ++colors;
            int n = v.popcount();
            n_normal += n;
            if (n < 8) {  // 8 個未満なら連結は 1 つだけ
                conn += connection_bonus(n);
                continue;
            }
            for (Bits rest = v; !rest.empty();) {
                Bits g = rest.lowest().expand(rest);
                conn += connection_bonus(g.popcount());
                rest = rest.andnot(g);
            }
        }
        int bonus = chain_bonus(result.chains) + conn + COLOR_BONUS[colors];
        result.score += 10 * n_normal * (bonus > 1 ? bonus : 1);

        Bits ojama = all.neighbors() & plane(OJAMA) & VISIBLE;
        remove_and_fall(all | ojama);
    }
}

SimResult simulate(const Field& f, const Pair& pair, Move m) {
    SimResult r{f, {}, 0};
    r.tear = r.field.place(pair, m);
    // 置いたぷよが 4 つ以上つながらなければ連鎖は起きない（Python 版と同じ判定）
    int x = m.x, cx = m.child_x();
    bool fires;
    if (x == cx) {
        int h = r.field.height(x);
        fires = r.field.connects4(x, h) || r.field.connects4(x, h - 1);
    } else {
        fires = r.field.connects4(x, r.field.height(x)) || r.field.connects4(cx, r.field.height(cx));
    }
    if (fires) r.chain = r.field.resolve_chain();
    return r;
}

std::vector<Move> legal_moves(const Field& f, const Pair& pair) {
    std::vector<Move> out;
    for (Move m : moves_for(pair))
        if (f.is_reachable(m)) out.push_back(m);
    return out;
}

}  // namespace puyo
