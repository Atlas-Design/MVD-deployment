variable "SD_EXPERIMENTS_HOME" {
    default = "$SD_EXPERIMENTS_HOME"
}

variable "REPOSITORY" {
    default = "europe-central2-docker.pkg.dev/unitydiffusion/sd-experiments"
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

    tags = ["${REPOSITORY}/sd_blender"]
}