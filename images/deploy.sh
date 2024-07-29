#!/usr/bin/env bash

set -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

if [[ "$1" == "--build" ]]; then
  "${SCRIPT_DIR}/build.sh"
fi

USERNAME=${USERNAME:=vprotasenia}
STAGE=${STAGE:=latest}

if [[ "$STAGE" == "stable" ]]; then
  GPU_QUEUE_HOSTNAMES=("34.77.198.247")
  CPU_QUEUE_HOSTNAMES=("34.77.198.247")
elif [[ "$STAGE" == "latest" ]]; then
  GPU_QUEUE_HOSTNAMES=("35.204.188.101")
  CPU_QUEUE_HOSTNAMES=("35.204.188.101")
else
  echo "STAGE can only be 'stable' or 'latest'"
  exit 1
fi


for CPU_QUEUE_HOSTNAME in "${CPU_QUEUE_HOSTNAMES[@]}"; do
  # shellcheck disable=SC2029
  ssh "${USERNAME}@${CPU_QUEUE_HOSTNAME}" "docker pull europe-central2-docker.pkg.dev/unitydiffusion/sd-experiments/sd_blender:${STAGE}"
done


for GPU_QUEUE_HOSTNAME in "${GPU_QUEUE_HOSTNAMES[@]}"; do
  # shellcheck disable=SC2029
  ssh "${USERNAME}@${GPU_QUEUE_HOSTNAME}" docker pull "europe-central2-docker.pkg.dev/unitydiffusion/sd-experiments/sd_comfywr:${STAGE}"
done