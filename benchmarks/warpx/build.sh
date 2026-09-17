#!/bin/bash
# Build WarpX (3D, MPI+OpenMP, openPMD, QED) into benchmarks/warpx/run/exe.
# The source tree (~300 MB, commit be2fff113, 2022-06-30) stays in memory-ef rather
# than being copied here. The binary in run/exe is the 2024-07-10 build from it.
# MPI-linked but run direct as one OpenMP process, like LULESH/AMG/SNAP.
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
SRC="${WARPX_SRC:-$HOME/projects/memory-ef/benchmarks/warpx/src}"
cd "$SRC"
rm -rf build
cmake -S . -B build
cmake --build build -j "$(nproc)"
mkdir -p "$D/run"
cp build/bin/warpx.3d.MPI.OMP.DP.OPMD.QED "$D/run/exe"
echo "installed -> $D/run/exe"
