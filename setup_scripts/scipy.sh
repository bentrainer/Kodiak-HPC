#!/bin/bash
SCIPY_VERSION="v1.14.0"
MKL_DIST="mkl-dynamic-ilp64-iomp"

if [[ -z "$(module list | grep gcc)" ]]; then
    echo "No GCC module found, try to load gcc/11.3.0."
    module load gcc/11.3.0
fi

if [[ -z "${CONDA_DEFAULT_ENV}" ]]; then
    echo "No conda environment detected, load python/3.10.4 as default."
    module load python/3.10.4
else
    echo "Detected conda environment ${CONDA_DEFAULT_ENV}."
fi
echo "Installing SciPy ${SCIPY_VERSION} for $(python -V)..."
sleep 3


TMPDIR=$(mktemp -d) && cd ${TMPDIR}

git clone https://github.com/scipy/scipy && cd scipy
git checkout tags/${SCIPY_VERSION}
git submodule update --init

CC=gcc python -m pip install . -Csetup-args=-Dblas=${MKL_DIST} -Csetup-args=-Dlapack=${MKL_DIST}

rm -rf ${TMPDIR}
