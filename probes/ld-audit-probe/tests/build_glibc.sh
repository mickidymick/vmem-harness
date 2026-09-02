#!/bin/bash
set -euo pipefail
S=/tmp/claude-1000/-home-jmcmicha-Projects/b3fef339-5cb6-4833-a6e8-2d1b6ada6993/scratchpad
cd "$S"

if [ ! -f glibc-2.35.tar.xz ]; then
    echo "== downloading glibc 2.35 =="
    curl -sSLO https://ftp.gnu.org/gnu/glibc/glibc-2.35.tar.xz
fi

[ -d glibc-2.35 ] || { echo "== extracting =="; tar xf glibc-2.35.tar.xz; }

mkdir -p build-2.35
cd build-2.35

if [ ! -f Makefile ]; then
    echo "== configuring =="
    ../glibc-2.35/configure \
        --prefix="$S/glibc-2.35-install" \
        --disable-werror \
        --disable-nscd \
        > configure.log 2>&1
fi

echo "== building (this is the long part) =="
make -j24 > build.log 2>&1

echo "== installing to prefix =="
make install > install.log 2>&1

echo "== DONE =="
"$S/glibc-2.35-install/lib/ld-linux-x86-64.so.2" --version | head -2
