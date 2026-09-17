#!/bin/bash
# Stage 654.roms_s for vbench (see ../_spec/stage.sh).
#
# roms tiles its grid for OpenMP: NtileI*NtileJ must be a multiple of the thread
# count, and SPEC rewrites the input for the run's thread count in pre_run()
# (Spec/object.pm, _calculate_dimensions). The uruguay run dir's input was generated
# for 24 threads (4x30); for vbench's 16 threads SPEC's algorithm gives NtileI=4,
# NtileJ=16. Generated here from the .x template, the same way SPEC does it.
set -euo pipefail
C="$HOME/Projects/benchmarks/cpu2017/benchspec/CPU"
R="$C/654.roms_s/run/run_base_refspeed_memory-ef-uruguay-m64.0000"
D="$(cd "$(dirname "$0")" && pwd)"
THREADS=16 NI=4 NJ=16      # keep in sync with machine.yaml omp_threads
"$D/../_spec/stage.sh" "$D" "$R/sroms_base.memory-ef-uruguay-m64" "$R" ocean_benchmark3.in.x varinfo.dat
rm -f "$D/run/ocean_benchmark3.in"
sed -E "s/^(\s+NtileI ==)\s+[0-9]+/\1 $NI/; s/^(\s+NtileJ ==)\s+[0-9]+/\1 $NJ/" \
    "$D/run/ocean_benchmark3.in.x" > "$D/run/ocean_benchmark3.in"
grep -E '^\s+Ntile[IJ] ==' "$D/run/ocean_benchmark3.in"
