#!/bin/bash
# Build QMCPACK 3.11.9 (CPU, SoA, mixed precision off) into benchmarks/qmcpack/run/exe,
# from the memory-ef source tree (too large to copy here). run/exe is the 2023-05-22
# build. MPI-linked, run direct as one OpenMP process.
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
SRC="${QMCPACK_SRC:-$HOME/projects/memory-ef/benchmarks/qmcpack/src}"
cd "$SRC" && rm -rf build && mkdir build && cd build
cmake -DCMAKE_C_COMPILER=mpicc -DCMAKE_CXX_COMPILER=mpicxx -DENABLE_SOA=1 \
      -DBUILD_UNIT_TESTS=False -DBUILD_SANDBOX=False -DBUILD_QMCTOOLS=False \
      -DHDF5_INCLUDE_DIR=/usr/include/hdf5/serial \
      -DHDF5_LIBRARIES=/usr/lib/x86_64-linux-gnu/libhdf5_serial_hl.so ..
make -j "$(nproc)"
mkdir -p "$D/run" && cp bin/qmcpack "$D/run/exe"
echo "installed -> $D/run/exe"
