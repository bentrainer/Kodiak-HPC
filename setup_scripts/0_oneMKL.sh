#!/bin/bash

# Little trick!
if [[ ! -f "/data/$(whoami)/opt/lib/libfakeintel.so" ]]; then
    TMPDIR=$(mktemp -d) && cd ${TMPDIR}
    echo "
    int mkl_serv_intel_cpu_true() {
        return 1;
    }" >> ${TMPDIR}/fakeintel.c
    gcc -shared -fPIC -o ${TMPDIR}/libfakeintel.so ${TMPDIR}/fakeintel.c
    mkdir -p /data/$(whoami)/opt/lib
    mv ${TMPDIR}/libfakeintel.so /data/$(whoami)/opt/lib/libfakeintel.so
    rm -rf ${TMPDIR}

    echo "---------------------------------------------------------------------------"
    echo "I put a 'libfakeintel.so' file under /data/$(whoami)/opt/lib,"
    echo "which may be helpful if you want to use oneMKL on AMD Zen machine."
    echo "Refer to https://danieldk.eu/Posts/2020-08-31-MKL-Zen for more information!"
fi
