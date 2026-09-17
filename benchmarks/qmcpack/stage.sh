#!/bin/bash
# Stage QMCPACK's NiO S64 inputs into benchmarks/qmcpack/run without copying data.
#
# The inputs next to memory-ef's qmcpack (Ni.opt.xml, O.xml, *.dat, ...) are git-LFS
# POINTER STUBS (~130 bytes), not data -- which is likely why QMCPACK runs from that
# tree never got past spline setup. The real pseudopotentials are in the QMCPACK
# source tree, mapped exactly as tests/performance/NiO does it:
#   Ni.opt.xml -> pseudopotentials_for_tests/Ni.opt.xml
#   O.xml      -> pseudopotentials_for_tests/O.ncpp.xml
# The NiO orbital h5 files (3.1 GB) are real and are symlinked, never copied.
set -euo pipefail
M="${QMCPACK_DATA:-$HOME/projects/memory-ef/benchmarks/qmcpack}"
P="$M/src/tests/pseudopotentials_for_tests"
D="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$D/run"
ln -sfn "$M/NiO" "$D/run/NiO"
ln -sfn "$P/Ni.opt.xml" "$D/run/Ni.opt.xml"
ln -sfn "$P/O.ncpp.xml" "$D/run/O.xml"
for f in "$D"/qmcpack_*.xml; do ln -sfn "$f" "$D/run/$(basename "$f")"; done
[ -x "$D/run/exe" ] || cp "$M/exe" "$D/run/exe"
echo "staged qmcpack -> $D/run"
