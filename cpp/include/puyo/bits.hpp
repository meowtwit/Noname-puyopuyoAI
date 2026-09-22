// フィールドのビット表現（書籍 3.2 FieldBits 相当）。
//
// 128bit = 8 レーン × 16bit。レーン x が列 x（0 と 7 は壁で常に 0）、レーン内の bit y が段 y。
//   up()    : 全体を 1 段上へ（(x, y) → (x, y+1)）
//   down()  : 1 段下へ
//   left()  : 1 列左へ（(x, y) → (x-1, y)）
//   right() : 1 列右へ
//
// バックエンド（コンパイル時に自動選択。PUYO_FORCE_PORTABLE で強制的に portable）:
//   PUYO_AVX2     : Bits は __m128i、Bits2（2 面同時）は __m256i。BMI2 の pext も使う
//   PUYO_SSE      : Bits は __m128i、Bits2 は Bits × 2
//   PUYO_PORTABLE : uint64_t × 2（ARM など）
#pragma once

#include <bit>
#include <cstdint>

#if defined(PUYO_SIMDE_AVX2)
// テスト用: SIMDe で AVX2 の経路を x86 以外（Apple Silicon など）でエミュレートして検証する
#define SIMDE_ENABLE_NATIVE_ALIASES
#include <simde/x86/avx2.h>
#define PUYO_AVX2 1
#define PUYO_SSE 1
#elif defined(PUYO_FORCE_PORTABLE)
#define PUYO_PORTABLE 1
#elif defined(__AVX2__)
#define PUYO_AVX2 1
#define PUYO_SSE 1
#elif defined(__SSE2__) || defined(_M_X64) || (defined(_M_IX86_FP) && _M_IX86_FP >= 2)
#define PUYO_SSE 1
#else
#define PUYO_PORTABLE 1
#endif

#if defined(PUYO_SSE) && !defined(PUYO_SIMDE_AVX2)
#include <immintrin.h>
#endif

#if defined(PUYO_AVX2) && !defined(PUYO_SIMDE_AVX2) && (defined(__BMI2__) || defined(_MSC_VER))
#define PUYO_BMI2 1
#endif

namespace puyo {

inline const char* backend_name() {
#if defined(PUYO_SIMDE_AVX2)
    return "avx2(simde)";
#elif defined(PUYO_AVX2)
#if defined(PUYO_BMI2)
    return "avx2+bmi2";
#else
    return "avx2";
#endif
#elif defined(PUYO_SSE)
    return "sse2";
#else
    return "portable";
#endif
}

// 16bit の pext（mask の立っているビットだけを下位へ詰める）
inline uint32_t pext16(uint32_t v, uint32_t mask) {
#if defined(PUYO_BMI2)
    return _pext_u32(v, mask);
#else
    uint32_t r = 0;
    for (uint32_t k = 1; mask; mask &= mask - 1, k <<= 1) {
        if (v & mask & (~mask + 1)) r |= k;
    }
    return r;
#endif
}

class Bits {
public:
#if defined(PUYO_SSE)
    Bits() : v_(_mm_setzero_si128()) {}
    explicit Bits(__m128i v) : v_(v) {}
    static Bits from_u64(uint64_t lo, uint64_t hi) {
        return Bits(_mm_set_epi64x(static_cast<long long>(hi), static_cast<long long>(lo)));
    }
    uint64_t lo() const { return static_cast<uint64_t>(_mm_cvtsi128_si64(v_)); }
    uint64_t hi() const { return static_cast<uint64_t>(_mm_cvtsi128_si64(_mm_unpackhi_epi64(v_, v_))); }
    __m128i raw() const { return v_; }

    Bits operator&(Bits o) const { return Bits(_mm_and_si128(v_, o.v_)); }
    Bits operator|(Bits o) const { return Bits(_mm_or_si128(v_, o.v_)); }
    Bits operator^(Bits o) const { return Bits(_mm_xor_si128(v_, o.v_)); }
    Bits andnot(Bits o) const { return Bits(_mm_andnot_si128(o.v_, v_)); }  // this & ~o
    Bits up() const { return Bits(_mm_slli_epi16(v_, 1)); }
    Bits down() const { return Bits(_mm_srli_epi16(v_, 1)); }
    Bits left() const { return Bits(_mm_srli_si128(v_, 2)); }
    Bits right() const { return Bits(_mm_slli_si128(v_, 2)); }
    bool operator==(Bits o) const { return _mm_movemask_epi8(_mm_cmpeq_epi8(v_, o.v_)) == 0xFFFF; }
    bool empty() const { return _mm_movemask_epi8(_mm_cmpeq_epi8(v_, _mm_setzero_si128())) == 0xFFFF; }
#else
    Bits() : lo_(0), hi_(0) {}
    static Bits from_u64(uint64_t lo, uint64_t hi) {
        Bits b;
        b.lo_ = lo;
        b.hi_ = hi;
        return b;
    }
    uint64_t lo() const { return lo_; }
    uint64_t hi() const { return hi_; }

    Bits operator&(Bits o) const { return from_u64(lo_ & o.lo_, hi_ & o.hi_); }
    Bits operator|(Bits o) const { return from_u64(lo_ | o.lo_, hi_ | o.hi_); }
    Bits operator^(Bits o) const { return from_u64(lo_ ^ o.lo_, hi_ ^ o.hi_); }
    Bits andnot(Bits o) const { return from_u64(lo_ & ~o.lo_, hi_ & ~o.hi_); }
    Bits up() const {
        constexpr uint64_t m = 0xFFFEFFFEFFFEFFFEull;
        return from_u64((lo_ << 1) & m, (hi_ << 1) & m);
    }
    Bits down() const {
        constexpr uint64_t m = 0x7FFF7FFF7FFF7FFFull;
        return from_u64((lo_ >> 1) & m, (hi_ >> 1) & m);
    }
    Bits left() const { return from_u64((lo_ >> 16) | (hi_ << 48), hi_ >> 16); }
    Bits right() const { return from_u64(lo_ << 16, (hi_ << 16) | (lo_ >> 48)); }
    bool operator==(Bits o) const { return lo_ == o.lo_ && hi_ == o.hi_; }
    bool empty() const { return (lo_ | hi_) == 0; }
#endif

    bool operator!=(Bits o) const { return !(*this == o); }
    int popcount() const { return std::popcount(lo()) + std::popcount(hi()); }

    static Bits bit(int x, int y) {
        int i = x * 16 + y;
        return i < 64 ? from_u64(uint64_t{1} << i, 0) : from_u64(0, uint64_t{1} << (i - 64));
    }
    bool test(int x, int y) const {
        int i = x * 16 + y;
        return i < 64 ? (lo() >> i) & 1 : (hi() >> (i - 64)) & 1;
    }
    uint32_t lane(int x) const {
        return static_cast<uint32_t>((x < 4 ? lo() >> (16 * x) : hi() >> (16 * (x - 4))) & 0xFFFF);
    }
    void to_lanes(uint16_t out[8]) const {
        uint64_t l = lo(), h = hi();
        for (int i = 0; i < 4; ++i) {
            out[i] = static_cast<uint16_t>(l >> (16 * i));
            out[i + 4] = static_cast<uint16_t>(h >> (16 * i));
        }
    }
    static Bits from_lanes(const uint16_t in[8]) {
        uint64_t l = 0, h = 0;
        for (int i = 0; i < 4; ++i) {
            l |= uint64_t{in[i]} << (16 * i);
            h |= uint64_t{in[i + 4]} << (16 * i);
        }
        return from_u64(l, h);
    }
    // 最下位のビットだけを残す
    Bits lowest() const {
        uint64_t l = lo();
        if (l) return from_u64(l & (~l + 1), 0);
        uint64_t h = hi();
        return from_u64(0, h & (~h + 1));
    }
    Bits neighbors() const { return up() | down() | left() | right(); }
    // this を種として mask 内で上下左右につながる範囲へ広げる
    Bits expand(Bits mask) const {
        Bits s = *this & mask;
        while (true) {
            Bits n = (s | s.neighbors()) & mask;
            if (n == s) return s;
            s = n;
        }
    }

    // (x = 1..6, y = lo..hi) の範囲
    static Bits rect(int y_lo, int y_hi) {
        uint64_t lane = ((uint64_t{1} << (y_hi + 1)) - 1) & ~((uint64_t{1} << y_lo) - 1);
        uint64_t l = (lane << 16) | (lane << 32) | (lane << 48);
        uint64_t h = lane | (lane << 16) | (lane << 32);
        return from_u64(l, h);
    }

private:
#if defined(PUYO_SSE)
    __m128i v_;
#else
    uint64_t lo_, hi_;
#endif
};

// 2 面分（例: 赤と緑）を同時に扱う 256bit。AVX2 では 1 命令で 2 面を処理する
class Bits2 {
public:
#if defined(PUYO_AVX2)
    Bits2(Bits a, Bits b) : v_(_mm256_inserti128_si256(_mm256_castsi128_si256(a.raw()), b.raw(), 1)) {}
    explicit Bits2(__m256i v) : v_(v) {}
    Bits first() const { return Bits(_mm256_castsi256_si128(v_)); }
    Bits second() const { return Bits(_mm256_extracti128_si256(v_, 1)); }
    Bits2 operator&(Bits2 o) const { return Bits2(_mm256_and_si256(v_, o.v_)); }
    Bits2 operator|(Bits2 o) const { return Bits2(_mm256_or_si256(v_, o.v_)); }
    Bits2 andnot(Bits2 o) const { return Bits2(_mm256_andnot_si256(o.v_, v_)); }
    Bits2 up() const { return Bits2(_mm256_slli_epi16(v_, 1)); }
    Bits2 down() const { return Bits2(_mm256_srli_epi16(v_, 1)); }
    Bits2 left() const { return Bits2(_mm256_srli_si256(v_, 2)); }   // 128bit レーンごとにシフト
    Bits2 right() const { return Bits2(_mm256_slli_si256(v_, 2)); }
    bool operator==(Bits2 o) const { return _mm256_movemask_epi8(_mm256_cmpeq_epi8(v_, o.v_)) == -1; }

private:
    __m256i v_;
#else
    Bits2(Bits a, Bits b) : a_(a), b_(b) {}
    Bits first() const { return a_; }
    Bits second() const { return b_; }
    Bits2 operator&(Bits2 o) const { return {a_ & o.a_, b_ & o.b_}; }
    Bits2 operator|(Bits2 o) const { return {a_ | o.a_, b_ | o.b_}; }
    Bits2 andnot(Bits2 o) const { return {a_.andnot(o.a_), b_.andnot(o.b_)}; }
    Bits2 up() const { return {a_.up(), b_.up()}; }
    Bits2 down() const { return {a_.down(), b_.down()}; }
    Bits2 left() const { return {a_.left(), b_.left()}; }
    Bits2 right() const { return {a_.right(), b_.right()}; }
    bool operator==(Bits2 o) const { return a_ == o.a_ && b_ == o.b_; }

private:
    Bits a_, b_;
#endif
public:
    Bits2 neighbors() const { return up() | down() | left() | right(); }
    Bits2 expand(Bits2 mask) const {
        Bits2 s = *this & mask;
        while (true) {
            Bits2 n = (s | s.neighbors()) & mask;
            if (n == s) return s;
            s = n;
        }
    }
};

// 同色の面 p のうち、4 つ以上つながっている部分（puyoai の vanishingSeed と同じ考え方）。
//   - 同色の隣接が 3 つ以上あるマスを含む連結は 4 個以上
//   - 隣接が 2 つ以上のマス同士が隣り合っていれば、その連結は 4 個以上
//   - 4 個以上の連結は必ず上のどちらかを含む（最大次数 2 なら 4 個以上の道か 2×2 の輪）
template <class B>
inline B vanishing(B p) {
    B u = p & p.down();   // 上に同色がある
    B d = p & p.up();     // 下に同色がある
    B l = p & p.right();  // 左に同色がある
    B r = p & p.left();   // 右に同色がある
    B ud_and = u & d, lr_and = l & r, ud_or = u | d, lr_or = l | r;
    B threes = (ud_and & lr_or) | (lr_and & ud_or);
    B twos = ud_and | lr_and | (ud_or & lr_or);
    B seed = threes | (twos & twos.up()) | (twos & twos.right());
    return seed.expand(p);
}

}  // namespace puyo
