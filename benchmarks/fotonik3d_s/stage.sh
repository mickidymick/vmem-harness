#!/bin/bash
# Stage 649.fotonik3d_s for vbench (see ../_spec/stage.sh).
C="$HOME/Projects/benchmarks/cpu2017/benchspec/CPU"
exec "$(dirname "$0")/../_spec/stage.sh" "$(cd "$(dirname "$0")" && pwd)" \
    "$C/649.fotonik3d_s/run/run_base_refspeed_memory-ef-uruguay-m64.0000/fotonik3d_s_base.memory-ef-uruguay-m64" "$C/649.fotonik3d_s/run/run_base_refspeed_memory-ef-uruguay-m64.0000" OBJ.dat incident_W3PC_25nm.def power1.dat power2.dat PSI.dat TEwaveguide.m trans_W3PC_25nm.def yee.dat
