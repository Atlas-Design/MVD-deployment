#!/usr/bin/env bash

set -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

#${SCRIPT_DIR}/build.sh

USERNAME=${USERNAME:-vprotasenia}

GPU_QUEUE_HOSTNAMES=("34.22.246.142")
CPU_QUEUE_HOSTNAMES=("34.22.246.142")

for CPU_QUEUE_HOSTNAME in ${CPU_QUEUE_HOSTNAMES[@]}; do
  ssh ${USERNAME}@${CPU_QUEUE_HOSTNAME} docker pull europe-central2-docker.pkg.dev/unitydiffusion/sd-experiments/sd_blender
done


for GPU_QUEUE_HOSTNAME in ${GPU_QUEUE_HOSTNAMES[@]}; do
  ssh ${USERNAME}@${GPU_QUEUE_HOSTNAME} docker pull europe-central2-docker.pkg.dev/unitydiffusion/sd-experiments/sd_comfywr
done