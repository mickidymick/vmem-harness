#!/bin/bash
# Stage 603.bwaves_s for vbench (see ../_spec/stage.sh).
C="$HOME/Projects/benchmarks/cpu2017/benchspec/CPU"
exec "$(dirname "$0")/../_spec/stage.sh" "$(cd "$(dirname "$0")" && pwd)" \
    "$C/603.bwaves_s/run/run_base_refspeed_memory-ef-uruguay-m64.0000/speed_bwaves_base.memory-ef-uruguay-m64" "$C/603.bwaves_s/run/run_base_refspeed_memory-ef-uruguay-m64.0000" bwaves_1.in bwaves_2.in
