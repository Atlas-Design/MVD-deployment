from dataclasses import dataclass, asdict

import os
import json
import shutil
import zipfile

import requests
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

        return logs
    except requests.exceptions.ReadTimeout:
        container.remove(force=True)
        raise
