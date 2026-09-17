#!/bin/bash
# Build one GAPBS kernel from its original source tree (github.com/sbeamer/gapbs @
# b5e3e19; g++ -O3 -fopenmp) and install it into a vbench bench dir. The source is
# NOT kept in this repo.
#   build.sh <kernel> <bench dir>
set -euo pipefail
K="$1"; DEST="$(cd "$2" && pwd)/run"
SRC="${GAPBS_SRC:-$HOME/Projects/benchmarks/gapbs}"
cd "$SRC"
make -j "$(nproc)" "$K"
mkdir -p "$DEST"
cp "$K" "$DEST/exe"
echo "installed $K -> $DEST/exe"
