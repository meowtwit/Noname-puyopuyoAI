"""C++ コア（cpp/）をビルドし、Python モジュールを puyo/ に置く。Windows / macOS / Linux 共通。

    python scripts/build_cpp.py                 # SIMD 自動選択（x86_64 → AVX2、ARM → portable）
    python scripts/build_cpp.py --simd SSE2     # SIMD を指定
    python scripts/build_cpp.py --selftest      # ビルド後に C++ 単体テスト（fixtures と照合）も実行
    python scripts/build_cpp.py --simd SIMDE --no-python --selftest --cmake-arg=-DPUYO_SIMDE_DIR=<simde>
                                                # Mac などで AVX2 の経路をエミュレートして検証

必要なもの: CMake 3.18+、C++20 コンパイラ（Windows は Visual Studio 2022）、pip install pybind11
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simd", default="AUTO", choices=["AUTO", "AVX2", "SSE2", "NATIVE", "PORTABLE", "SIMDE"])
    ap.add_argument("--build-dir", default=None)
    ap.add_argument("--no-python", action="store_true", help="Python モジュールを作らない（selftest のみ）")
    ap.add_argument("--selftest", action="store_true", help="ビルド後に selftest を実行")
    ap.add_argument("--cmake-arg", action="append", default=[], help="CMake に追加で渡す引数")
    a = ap.parse_args()

    build = Path(a.build_dir) if a.build_dir else ROOT / "build" / a.simd.lower()
    cfg = [
        "cmake", "-S", str(ROOT / "cpp"), "-B", str(build),
        f"-DPUYO_SIMD={a.simd}",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        f"-DPUYO_BUILD_PYTHON={'OFF' if a.no_python else 'ON'}",
        f"-DPython_EXECUTABLE={sys.executable}",
    ]
    if not a.no_python:
        import pybind11

        cfg.append(f"-Dpybind11_DIR={pybind11.get_cmake_dir()}")
    run(cfg + a.cmake_arg)
    run(["cmake", "--build", str(build), "--config", "Release", "--parallel"])

    if a.selftest:
        exe = next(p for p in (build / "selftest", build / "Release" / "selftest.exe", build / "selftest.exe") if p.exists())
        run([str(exe), str(ROOT / "tests" / "fixtures" / "cpp_fixtures.txt")])


if __name__ == "__main__":
    main()
