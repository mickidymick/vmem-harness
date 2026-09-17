#!/bin/bash
# Build LULESH 2.0 from its original source tree and install it at
# benchmarks/lulesh/run/exe. The source is NOT kept in this repo.
#
# NOTE: the source's Makefile sets CXX = $(MPICXX), so this produces an MPI-LINKED
# binary even though the harness runs it direct as single-process OpenMP. That is
# deliberate for now -- it matches the exe all prior -s300 results were taken with.
# The cost is that OpenMPI's singleton init exec's a helper daemon that inherits
# LD_PRELOAD and becomes a second vmem client; the runtime's per-pid stats files
# keep that harmless. For a clean single-process build instead, set CXX = $(SERCXX)
# (g++ -DUSE_MPI=0) -- but that changes the binary, so re-measure the footprint and
# re-run every condition, never mix the two in one ladder.
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
SRC="${LULESH_SRC:-$HOME/projects/memory-ef/benchmarks/lulesh/src}"
cd "$SRC"
make clean
make -j "$(nproc)"
mkdir -p "$D/run"
cp lulesh2.0 "$D/run/exe"
echo "installed -> $D/run/exe"
