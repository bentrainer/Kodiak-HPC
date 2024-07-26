#!/bin/bash
MKLURL="https://registrationcenter-download.intel.com/akdlm/IRC_NAS/cdff21a5-6ac7-4b41-a7ec-351b5f9ce8fd/l_onemkl_p_2024.2.0.664_offline.sh"

if [[ ! -z "${MKLROOT}" ]]; then
    echo "MKL exists!"
    read -p "Update? [Y/N] " -n 1 -r
    echo

    if [[ ! $REPLY =~ ^[Yy] ]]; then
        echo "Exit!"
        exit 0
    fi

else
    echo "Install MKL to /data/$(whoami)/opt/oneAPI..."
    mkdir -p /data/$(whoami)/opt/oneAPI
fi


TMPDIR=$(mktemp -d)

echo -e "\nDownloading...\n"
curl -L "${MKLURL}" -o "${TMPDIR}/l_onemkl_offline.sh"
chmod +x "${TMPDIR}/l_onemkl_offline.sh"


"${TMPDIR}/l_onemkl_offline.sh" \
  -f "${TMPDIR}" -a \
  --action install --cli --eula accept \
  --install-dir /data/$(whoami)/opt/oneAPI \
  --silent


rm -rf "${TMPDIR}"


# check bashrc
if grep -Fq "oneAPI/setvars.sh" ~/.bashrc
then
    echo "~/.bashrc checked!"
else
    echo "Add setvars.sh to ~/.bashrc!"
    echo -e "\n\nsource /data/$(whoami)/opt/oneAPI/setvars.sh" >> ~/.bashrc
fi

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
else
    echo "Ciallo～(∠・ω< )⌒★"
fi
