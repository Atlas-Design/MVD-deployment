variable "SD_EXPERIMENTS_HOME" {
    default = "SD_EXPERIMENTS_HOME"
}

variable "REPOSITORY" {
    default = "europe-central2-docker.pkg.dev/unitydiffusion/sd-experiments"
}

group "default" {
    targets = ["cloud"]
}

target "local" {
    context = "${SD_EXPERIMENTS_HOME}/comfywr"
    dockerfile = "Dockerfile"
}

target "cloud" {
    dockerfile = "comfywr.Dockerfile"
    contexts = {
        local = "target:local",
        root = "${SD_EXPERIMENTS_HOME}/",
        comfywr-root = "${SD_EXPERIMENTS_HOME}/comfywr"
    }

    tags = ["${REPOSITORY}/sd_comfywr"]
}