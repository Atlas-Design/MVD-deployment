variable "SD_EXPERIMENTS_HOME" {
    default = "$SD_EXPERIMENTS_HOME"
}

variable "REPOSITORY" {
    default = "europe-central2-docker.pkg.dev/unitydiffusion/sd-experiments"
}

variable "STAGE" {
    default = "latest"
}

group "default" {
    targets = ["cloud"]
}

target "local" {
    context = "${SD_EXPERIMENTS_HOME}"
    dockerfile = "Dockerfile"
}

target "cloud" {
    dockerfile = "blender.Dockerfile"
    contexts = {
        local = "target:local",
        root = "${SD_EXPERIMENTS_HOME}"
    }

    tags = ["${REPOSITORY}/sd_blender:${STAGE}"]

    cache-to = ["type=registry,ref=${REPOSITORY}/sd_blender_cache:${STAGE},mode=max"]
    cache-from = ["type=registry,ref=${REPOSITORY}/sd_blender_cache:${STAGE}", "type=registry,ref=${REPOSITORY}/sd_blender_cache:latest"]
}