#!/usr/bin/env bash

set -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

function build() {
  cd "${SCRIPT_DIR}"

  export SD_EXPERIMENTS_HOME=${SD_EXPERIMENTS_HOME:=../../sd_experiments}

  docker buildx bake -f blender.docker-bake.hcl --push
  docker buildx bake -f comfywr.docker-bake.hcl --push
}

build