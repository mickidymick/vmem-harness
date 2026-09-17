#!/bin/bash
# Build AMG (CORAL-2) from its original source tree and install it at
# benchmarks/amg/run/exe. The source is NOT kept in this repo.
#
# Makefile.include sets CC = mpicc, so this is an MPI-LINKED binary even though the
# harness runs it direct as single-process OpenMP. Same situation as LULESH: the
# OpenMPI singleton helper becomes a second vmem client, which per-pid stats files
# make harmless. Rebuilding changes the binary -- re-measure the footprint and re-run
# every condition; never mix binaries in one ladder.
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
SRC="${AMG_SRC:-$HOME/Projects/benchmarks/amg/src}"
cd "$SRC"
make clean
make -j "$(nproc)"
mkdir -p "$D/run"
cp test/amg "$D/run/exe"
echo "installed -> $D/run/exe"
