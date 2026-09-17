#!/bin/bash
# Stage 619.lbm_s for vbench (see ../_spec/stage.sh).
C="$HOME/Projects/benchmarks/cpu2017/benchspec/CPU"
exec "$(dirname "$0")/../_spec/stage.sh" "$(cd "$(dirname "$0")" && pwd)" \
    "$C/619.lbm_s/build/build_base_memory-ef-uruguay-m64.0000/lbm_s" "$C/619.lbm_s/data/refspeed/input" 200_200_260_ldc.of
