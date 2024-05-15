#!/usr/bin/env bash

set -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

export STAGE=${STAGE:=latest}

function build() {
  cd "${SCRIPT_DIR}"

  export SD_EXPERIMENTS_HOME=${SD_EXPERIMENTS_HOME:=../../sd_experiments}

  trap "docker buildx rm container" EXIT INT
  docker buildx create --name=container --driver=docker-container --bootstrap

  docker buildx bake -f blender.docker-bake.hcl --progress plain --push --builder=container
  echo "----------------------------------------------------------------------------------"
  docker buildx bake -f comfywr.docker-bake.hcl --progress plain --push --builder=container
}

build