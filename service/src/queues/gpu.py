import os
import shutil

import docker
import docker.types
from celery import Celery

from settings import settings
from queues.base import AnyStageInput, get_tmp_dir, save_context, load_context, save_data, load_data

queue = Celery(
    'gpu',
    broker=settings.RABBITMQ_URL,
    backend=settings.REDIS_URL
)
queue.conf.task_default_queue = 'gpu'
queue.conf.broker_connection_retry = True
queue.conf.broker_connection_retry_on_startup = False
queue.conf.task_track_started = True


def run_docker_command(context: dict, command: str):
    client = docker.from_env()

    return client.containers.run(
        f"europe-central2-docker.pkg.dev/unitydiffusion/sd-experiments/sd_comfywr:{settings.QUEUE_IMAGE_TAG.value}",
        command=[
            'bash', '-ex', '-c',
            command.format(**context)
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
        stdout=True,
        stderr=True,

        device_requests=[
            docker.types.DeviceRequest(
                capabilities=[['gpu']]
            )
        ],

        remove=True,
    )


@queue.task(typing=True)
def stage_2(raw_input: dict) -> dict:
    input = AnyStageInput(**raw_input)

    tmp_dir = get_tmp_dir(input.job_id)
    load_data(tmp_dir, input.job_id)
    context = load_context(tmp_dir)

    context["generated_textures_path"] = os.path.join(context["output_dir"], context["config_filename"], "02_gen_textures")

    result = run_docker_command(
        context,
        'python3 /workdir/sd_scripts/generate_textures.py '
        '/workdir/{prior_renders_path} '
        '/workdir/{generated_textures_path} '
        '--config /workdir/{config_path} ',
    )
    print(f"{result=}")

    save_context(tmp_dir, context)
    save_data(tmp_dir, input.job_id)
    shutil.rmtree(tmp_dir)

    return {}

