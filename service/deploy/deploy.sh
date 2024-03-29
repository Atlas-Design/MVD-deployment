#!/usr/bin/bash

set -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

USERNAME=${USERNAME:-vprotasenia}
MANAGER_HOSTNAME=34.140.119.26

function deploy() {
  cd "${SCRIPT_DIR}"

  docker build .. -t europe-central2-docker.pkg.dev/unitydiffusion/sd-experiments/service
  docker push europe-central2-docker.pkg.dev/unitydiffusion/sd-experiments/service

  docker -H ssh://${USERNAME}@${MANAGER_HOSTNAME} stack deploy -c docker-compose.yaml --detach=true --resolve-image always --with-registry-auth --prune "sd-experiments"
}

deploy