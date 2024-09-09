#!/bin/bash

IPREFIX=/data/$(whoami)/opt
ZENVER=$(cat /proc/cpuinfo | grep EPYC | grep -Po "(?<=[0-9]{3})[0-9]" | head -1)

if [[ -z "${ZENVER}" ]]; then
    echo "This script should be run on an EPYC machine!"
    exit 1
fi

if [[ -z "$(which clang)" || -z "$(which clang++)" ]]; then
    echo "No clang/clang++ found!"
    exit 1
fi

# BLIS
./configure --prefix=${IPREFIX} --enable-static --enable-shared \
    --enable-cblas --enable-threading=openmp --complex-return=intel \
    CC=clang CXX=clang++ zen

# libFLAME
export CC=clang
export FC=flang
export FLIBS="-lflang"
./configure --prefix=${IPREFIX} \
    --enable-amd-flags --enable-amd-aocc-flags --enable-amd-opt \
    --enable-optimizations="-march=znver${ZENVER} -O3" \
    --enable-lapack2flame --enable-cblas-interfaces --enable-static-build \
    LIBS="-lblas -lblis-mt" LDFLAGS=-L${IPREFIX}/lib

echo "Example usage:
  export BLAS_VERSION=${IPREFIX}/lib/libblis.so
  export LAPACK_VERSION=${IPREFIX}/lib/libflame.so
before running matlab.
"


if [[ -z "$(grep BLAS_VERSION ~/.bashrc)" ]]; then

    echo "Modified ~/.bashrc!"
    echo -e "
if [[ ! -z \"\$(cat /proc/cpuinfo | grep EPYC)\" ]]; then
    export BLAS_VERSION=${IPREFIX}/lib/libblis.so
    export LAPACK_VERSION=${IPREFIX}/lib/libflame.so
fi
" | tee --append ~/.bashrc

fi