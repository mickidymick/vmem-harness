#!/bin/bash
# Build SNAP (LANL SN transport proxy, v1.10) from its original source tree and
# install it at benchmarks/snap/run/exe. The source is NOT kept in this repo.
#
# mpif90 + -fopenmp: an MPI-linked binary run direct as one OpenMP process
# (npey=npez=1), same situation as LULESH/AMG. Threads come from `nthreads` in the
# input file, NOT OMP_NUM_THREADS -- the inputs here are set to 16 (the harness's
# omp_threads); the memory-ef originals said 30.
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
SRC="${SNAP_SRC:-$HOME/projects/memory-ef/benchmarks/snap/src/src}"
cd "$SRC"
make clean
make -j "$(nproc)"
mkdir -p "$D/run"
cp gsnap "$D/run/exe"
echo "installed -> $D/run/exe"
