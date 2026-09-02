#!/bin/bash
# Build LULESH and install it where the harness expects it: benchmarks/lulesh/run/exe.
# (The pre-reorg version copied to ../exe and called an undefined `corecount`.)
#
# NOTE: src/Makefile line 13 sets CXX = $(MPICXX), so this produces an MPI-LINKED
# binary even though the harness runs it direct as single-process OpenMP. That is
# deliberate for now -- it matches the exe all prior -s300 results were taken with.
# The cost is that OpenMPI's singleton init exec's a helper daemon that inherits
# LD_PRELOAD and becomes a second vmem client; the runtime's per-pid stats files
# keep that harmless. For a clean single-process build instead, set CXX = $(SERCXX)
# (g++ -DUSE_MPI=0) in src/Makefile -- but that changes the binary, so re-measure
# the footprint and re-run every condition, never mix the two in one ladder.
set -euo pipefail
cd "$(dirname "$0")/src"
make clean
make -j "$(nproc)"
mkdir -p ../run
cp lulesh2.0 ../run/exe
echo "installed -> $(cd .. && pwd)/run/exe"
