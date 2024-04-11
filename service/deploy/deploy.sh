#!/usr/bin/bash

set -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

export STAGE=${STAGE:=latest}

if [[ "$STAGE" == "stable" ]]; then
  export OUTPORT=3000
elif [[ "$STAGE" == "latest" ]]; then
  export OUTPORT=3001
else
  echo "STAGE can only be 'stable' or 'latest'"
  exit 1
fi

USERNAME=${USERNAME:-vprotasenia}
MANAGER_HOSTNAME=34.140.119.26

function deploy() {
  cd "${SCRIPT_DIR}"

  docker build .. -t europe-central2-docker.pkg.dev/unitydiffusion/sd-experiments/service:${STAGE}
  docker push europe-central2-docker.pkg.dev/unitydiffusion/sd-experiments/service:${STAGE}

  docker -H ssh://${USERNAME}@${MANAGER_HOSTNAME} stack deploy -c docker-compose.yaml --detach=true --resolve-image always --with-registry-auth --prune "sd-experiments-${STAGE}"
}

deploy