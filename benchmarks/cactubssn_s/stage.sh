#!/bin/bash
# Stage 607.cactuBSSN_s for vbench (see ../_spec/stage.sh).
C="$HOME/Projects/benchmarks/cpu2017/benchspec/CPU"
exec "$(dirname "$0")/../_spec/stage.sh" "$(cd "$(dirname "$0")" && pwd)" \
    "$C/607.cactuBSSN_s/run/run_base_refspeed_memory-ef-uruguay-m64.0000/cactuBSSN_s_base.memory-ef-uruguay-m64" "$C/607.cactuBSSN_s/run/run_base_refspeed_memory-ef-uruguay-m64.0000" spec_ref.par
