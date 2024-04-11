#!/usr/bin/env bash

set -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

#${SCRIPT_DIR}/build.sh

USERNAME=${USERNAME:-vprotasenia}

if [[ "$STAGE" == "stable" ]]; then
  GPU_QUEUE_HOSTNAMES=("34.77.198.247")
  CPU_QUEUE_HOSTNAMES=("34.77.198.247")
elif [[ "$STAGE" == "latest" ]]; then
  GPU_QUEUE_HOSTNAMES=("34.22.246.142")
  CPU_QUEUE_HOSTNAMES=("34.22.246.142")
else
  echo "STAGE can only be 'stable' or 'latest'"
  exit 1
fi


for CPU_QUEUE_HOSTNAME in ${CPU_QUEUE_HOSTNAMES[@]}; do
  ssh ${USERNAME}@${CPU_QUEUE_HOSTNAME} docker pull europe-central2-docker.pkg.dev/unitydiffusion/sd-experiments/sd_blender:${STAGE}
done


for GPU_QUEUE_HOSTNAME in ${GPU_QUEUE_HOSTNAMES[@]}; do
  ssh ${USERNAME}@${GPU_QUEUE_HOSTNAME} docker pull europe-central2-docker.pkg.dev/unitydiffusion/sd-experiments/sd_comfywr:${STAGE}
done