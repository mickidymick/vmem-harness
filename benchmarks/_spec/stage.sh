#!/bin/bash
# Stage a SPEC CPU2017 benchmark into a vbench run dir WITHOUT copying SPEC data:
# inputs are symlinked from the SPEC install (SPEC is licensed -- nothing from it
# may be committed; .gitignore excludes benchmarks/*/run/* except footprint.txt).
#
#   stage.sh <bench dir> <binary> <input dir> <input file>...
#
# Also links run/spec -> the SPEC install, so a bench's `validate` can call
# spec/bin/harness/specdiff against spec/benchspec/CPU/*/data/refspeed/output.
# The binaries were built 2022-07-21 with config memory-ef-uruguay (gcc/gfortran,
# OpenMP); vbench uses them as-is rather than rebuilding through runcpu.
set -euo pipefail
SPEC="${SPEC:-$HOME/Projects/benchmarks/cpu2017}"
name="$(basename "$1")"; dest="$1/run"; bin="$2"; src="$3"; shift 3
[ -x "$bin" ] || { echo "no binary: $bin" >&2; exit 1; }
mkdir -p "$dest"
for f in "$@"; do
    [ -e "$src/$f" ] || { echo "missing input: $src/$f" >&2; exit 1; }
    ln -sfn "$src/$f" "$dest/$f"
done
cp "$bin" "$dest/exe"
ln -sfn "$SPEC" "$dest/spec"
echo "staged $name -> $dest"
