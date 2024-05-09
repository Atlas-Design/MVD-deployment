from dataclasses import dataclass, asdict

import os
import json
import shutil
import zipfile

import requests
import docker
import docker.types
import docker.models.containers
from google.cloud import storage

from settings import settings


@dataclass
class AnyStageInput:
    job_id: str

    asdict = asdict


def get_tmp_dir(job_id: str) -> str:
    path = os.path.join("/tmp", job_id)
    os.makedirs(path, exist_ok=True)
    return path


def save_context(tmp_dir: str, context: dict) -> None:
    with open(os.path.join(tmp_dir, 'job', 'context'), 'w') as context_file:
        context_file.write(json.dumps(context))


def load_context(tmp_dir: str) -> dict:
    with open(os.path.join(tmp_dir, 'job', 'context'), 'r') as context_file:
        return json.load(context_file)


def save_data(tmp_dir: str, job_id: str) -> None:
    client_storage = storage.Client()

    zip_filename = shutil.make_archive(os.path.join(tmp_dir, 'data'), 'zip', os.path.join(tmp_dir), 'job')

    data_bucket = client_storage.bucket(settings.SD_DATA_STORAGE_BUCKET_NAME)

    data_blob = data_bucket.blob(f"{job_id}/data.zip")
    data_blob.upload_from_filename(zip_filename)


def load_data(tmp_dir: str, job_id: str) -> None:
    client_storage = storage.Client()

    data_bucket = client_storage.bucket(settings.SD_DATA_STORAGE_BUCKET_NAME)

    data_blob = data_bucket.blob(f"{job_id}/data.zip")
    data_blob.download_to_filename(os.path.join(tmp_dir, 'data.zip'))

    with zipfile.ZipFile(os.path.join(tmp_dir, 'data.zip')) as zf:
        zf.extractall(os.path.join(tmp_dir))


def wait_docker_exit(container: docker.models.containers.Container) -> str:
    try:
        logs = ''
        for log in container.logs(timestamps=True, stream=True):
            logs += log.decode()

        # TODO: This is a temporary fix, should handle this in a better way
        if 'Traceback' in logs:
            raise Exception(f"Error in logs: {logs}")
        elif 'ExitCodeError' in logs:
            raise Exception(f"Non-zero exit code: {logs}")

        return logs
    except requests.exceptions.ReadTimeout:
        container.remove(force=True)
        raise


def run_docker_command(image: str, context: dict, command: str, with_gpu: bool) -> docker.models.containers.Container:
    client = docker.from_env()

    return client.containers.run(
        image,
        command=[
            'bash', '-ex', '-c',
            """trap '[ "$?" -ne 0 ] && echo \\Exit\\Code\\Error' ERR""" + "; " + command.format(**context)
        ],
        volumes=[
            f'{context["local_input_dir"]}:{context["docker_input_dir"]}',
            f'{context["local_output_dir"]}:{context["docker_output_dir"]}',

            # Note: Needed for style images to be consumed correctly
            f'{context["local_output_dir"]}:/workdir/blender_workdir/job/output',
        ],
        environment={
            "OPENCV_IO_ENABLE_OPENEXR": 1
        },

        stdout=False,
        stderr=False,

        remove=True,
        detach=True,

        device_requests=[
            docker.types.DeviceRequest(
                capabilities=[['gpu']]
            )
        ] if with_gpu else [],
    )


def run_comfywr_docker_command(context: dict, command: str, with_gpu: bool = False) -> docker.models.containers.Container:
    return run_docker_command(
        f"europe-central2-docker.pkg.dev/unitydiffusion/sd-experiments/sd_comfywr:{settings.QUEUE_IMAGE_TAG.value}",
        context, command,
        with_gpu,
    )


def run_blender_docker_command(context: dict, command: str, with_gpu: bool = False) -> docker.models.containers.Container:
    return run_docker_command(
        f"europe-central2-docker.pkg.dev/unitydiffusion/sd-experiments/sd_blender:{settings.QUEUE_IMAGE_TAG.value}",
        context, command,
        with_gpu,
    )


def generate_blender_command(command: str, opts: str) -> str:
    return f'blender --python-exit-code 1 --background --python blender_scripts/{command} -- {opts} --config {{config_path}}'
