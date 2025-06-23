#!/bin/bash
# Usage:
# ./0_AOCL.sh -> Build & install into /data/$(whoami)/opt
# IPREFIX=somewhere_else ./0_AOCL.sh -> Build & install into somewhere_else

function wait_info {
    echo -n "$@"
    for k in {1..3}
    do
        echo -n "."
        sleep 1
    done
    echo ""
}

function get_github_source_url {
    API_URL="https://api.github.com/repos/$1/releases/latest"
    TGZ_URL=$(curl -s "$API_URL" | grep '"tarball_url":' | cut -d '"' -f 4)
    echo "${TGZ_URL}"
}


ZENVER=$(cat /proc/cpuinfo | grep EPYC | grep -Po "(?<=[0-9]{3})[0-9]" | head -1)
if [[ -z "${ZENVER}" ]]; then
    echo "This script should be run on an EPYC machine!"
    exit 1
fi

if [[ -z "${IPREFIX}" ]]; then
    IPREFIX=/data/$(whoami)/opt
fi

echo "Prefix=${IPREFIX}"

if [[ -z "$(which cmake)" ]]; then
    echo "No CMAKE found!"
    exit 1
fi

if [[ -z "$(clang --version | grep AOCC)" || -z "$(clang++ --version | grep AOCC)" ]]; then
    echo "No AOCC found!"
    exit 1
fi


TMP_DIR=$(mktemp -d)


# AOCLUtils
wait_info "Build & install AOCLUtils"
AOCL_URL=$(get_github_source_url amd/aocl-utils)
echo "Download AOCLUtils source code from: ${AOCL_URL}"

curl -L "${AOCL_URL}" -o "${TMP_DIR}/aocl-utils.tar.gz"
tar -xzvf "${TMP_DIR}/aocl-utils.tar.gz" -C "${TMP_DIR}"

cd "${TMP_DIR}/amd-aocl-utils"*
cmake -B default "-DCMAKE_INSTALL_PREFIX=${IPREFIX}" \
  && cmake --build default --config release -j$(nproc) \
  && cmake --install default --config release \
  && echo "Success!" && echo ""


# BLIS
wait_info "Build & install BLIS"
BLIS_URL=$(get_github_source_url amd/blis)
echo "Download BLIS source code from: ${AOCL_URL}"

curl -L "${BLIS_URL}" -o "${TMP_DIR}/blis.tar.gz"
tar -xzvf "${TMP_DIR}/blis.tar.gz" -C "${TMP_DIR}"

cd "${TMP_DIR}/amd-blis"*
cmake . "-DCMAKE_INSTALL_PREFIX=${IPREFIX}" \
  -DBLIS_CONFIG_FAMILY=amdzen CC=clang CXX=clang++ \
  -DCOMPLEX_RETURN=intel \
  -DENABLE_BLAS=ON -DENABLE_CBLAS=ON \
  -DENABLE_THREADING=openmp \
  -DCMAKE_BUILD_TYPE=Release \
  \
  && cmake --build . --config Release -j$(nproc) \
  && cmake --install . --config Release \
  && echo "Success!" && echo ""

# FLAME
wait_info "Build & install libFLAME"
FLAME_URL=$(get_github_source_url amd/libflame)
echo "Download libFLAME source code from: ${AOCL_URL}"

curl -L "${FLAME_URL}" -o "${TMP_DIR}/flame.tar.gz"
tar -xzvf "${TMP_DIR}/flame.tar.gz" -C "${TMP_DIR}"

cd "${TMP_DIR}/amd-libflame"* && mkdir newbuild && cd newbuild
CC=clang FC=flang FLIBS="-lflang" \
  cmake ../ "-DCMAKE_INSTALL_PREFIX=${IPREFIX}" \
  "-DAOCL_ROOT=${IPREFIX}" \
  "-DLIBAOCLUTILS_INCLUDE_PATH=${IPREFIX}/include" \
  "-DLIBAOCLUTILS_LIBRARY_PATH=${IPREFIX}/lib64/libaoclutils.a" \
  -DENABLE_EMBED_AOCLUTILS=ON \
  -DENABLE_AMD_FLAGS=ON -DENABLE_AMD_AOCC_FLAGS=ON \
  -DLF_ISA_CONFIG=AVX2 \
  -DENABLE_AOCL_BLAS=ON \
  \
  && cmake --build . --config Release -j$(nproc) \
  && cmake --install . --config Release \
  && echo "Success!" && echo ""


# Clean up
wait_info "Clean up"
rm -rf "${TMP_DIR}"

echo ""

echo "Example usage:
  export BLAS_VERSION=${IPREFIX}/lib/libblis-mt.so
  export LAPACK_VERSION=${IPREFIX}/lib/libflame.so
before running matlab.
"


if [[ -z "$(grep BLAS_VERSION ~/.bashrc)" ]]; then

    echo "Modified ~/.bashrc!"
    echo -e "
if [[ ! -z \"\$(cat /proc/cpuinfo | grep EPYC)\" ]]; then
    export BLAS_VERSION=\"${IPREFIX}/lib/libblis-mt.so\"
    export LAPACK_VERSION=\"${IPREFIX}/lib/libflame.so\"
fi
" | tee --append ~/.bashrc

fi