import shutil
import zipfile
from typing import List
from dataclasses import dataclass

import os
from itertools import chain

import docker
from celery import Celery

from settings import settings
from queues.base import AnyStageInput, get_tmp_dir, save_context, load_context, load_data, save_data

from celery.utils.log import get_task_logger
logger = get_task_logger(__name__)

queue = Celery(
    'cpu',
    broker=settings.RABBITMQ_URL,
    backend=settings.REDIS_URL
)
queue.conf.task_default_queue = 'cpu'
queue.conf.broker_connection_retry = True
queue.conf.broker_connection_retry_on_startup = False
queue.conf.task_track_started = True


def run_docker_command(context: dict, command: str):
    client = docker.from_env()

    return client.containers.run(
        f"europe-central2-docker.pkg.dev/unitydiffusion/sd-experiments/sd_blender:{settings.QUEUE_IMAGE_TAG.value}",
        command=[
            'bash', '-ex', '-c',
            command.format(**context)
        ],
        volumes=[
            f'{context["local_input_dir"]}:{context["docker_input_dir"]}',
            f'{context["local_output_dir"]}:{context["docker_output_dir"]}',

            # Needed for style images to be consumed correctly
            f'{context["local_output_dir"]}:/workdir/blender_workdir/job/output',
        ],
        environment={
            "OPENCV_IO_ENABLE_OPENEXR": 1
        },
        stdout=True,
        stderr=True,

        remove=True,
    )


@dataclass
class PreStage0Input(AnyStageInput):
    pos_prompt: str
    neg_prompt: str
    prompt_strength: float
    random_seed: float
    disable_displacement: bool
    texture_resolution: int
    generation_size_multiplier: float
    # input_mesh: str
    style_images_paths: List[str]
    style_images_weights: List[float]
    shadeless_strength: float
    loras: List[str]
    loras_weights: List[float]

    stage_1_steps: int
    stage_2_steps: int
    disable_3d: bool
    disable_upscaling: bool

    organic: bool
    apply_displacement_to_mesh: bool
    direct_config_override: str


@queue.task(typing=True)
def prestage_0(raw_input: dict) -> dict:
    logger.info("Running prestage_0")

    input = PreStage0Input(**raw_input)

    tmp_dir = get_tmp_dir(input.job_id)

    context = {
        'tmp_dir': tmp_dir,

        "local_output_dir": os.path.join(tmp_dir, 'job', 'output'),
        "local_input_dir": os.path.join(tmp_dir, 'job', 'input'),

        "docker_output_dir": "/workdir/job/output",
        "docker_input_dir": "/workdir/job/input",

        "config_path": "/workdir/job/output/generated_config.py",
        "config_filename": "generated_config",
    }

    pos_prompt = input.pos_prompt.strip("'")
    neg_prompt = input.neg_prompt.strip("'")

    generate_config_args = [
        '--workdir', '{docker_output_dir}',

        '--pos_prompt', f"'{pos_prompt}'",
        '--neg_prompt', f"'{neg_prompt}'",
        '--prompt_strength', str(input.prompt_strength),
        '--random_seed', str(input.random_seed),

        *['--disable_displacement' if input.disable_displacement else ''],

        '--texture_resolution', str(input.texture_resolution),
        '--generation_size_multiplier', str(input.generation_size_multiplier),
        '--input_mesh', '{docker_input_dir}/input_mesh.obj',
        *list(chain.from_iterable(
            [
                ['--style_images_paths', f'{os.path.join(context["docker_input_dir"], "style_images", path)}']
                for path in input.style_images_paths
            ]
        )),
        *list(chain.from_iterable(
            [
                ['--style_images_weights', f'{weight}']
                for weight in input.style_images_weights
            ]
        )),
        '--shadeless_strength', str(input.shadeless_strength),
        *list(chain.from_iterable([['--loras', f'{lora}'] for lora in input.loras])),
        *list(chain.from_iterable([['--loras_weights', f'{weight}'] for weight in input.loras_weights])),

        '--stage_1_steps', str(input.stage_1_steps),
        '--stage_2_steps', str(input.stage_2_steps),

        *['--disable_3d' if input.disable_3d else ''],
        *['--disable_upscaling' if input.disable_upscaling else ''],

        *['--organic' if input.organic else ''],
        *['--apply_displacement_to_mesh' if input.apply_displacement_to_mesh else ''],

        '--direct_config_override', input.direct_config_override,
    ]

    load_data(tmp_dir, input.job_id)

    result = run_docker_command(
        context,
        ' '.join([
            "${{BLENDERPY}}", "/workdir/tools/config_generator.py",
            *generate_config_args
        ]) + " > /workdir/job/output/runtime_params_raw"
    )
    logger.info(f"{result=}")

    with open(os.path.join(context["local_output_dir"], 'runtime_params_raw'), 'r') as runtime_params_raw_file:
        runtime_params_raw = runtime_params_raw_file.readline().rstrip()

        runtime_params_split = runtime_params_raw.split(' ')[1:]

        print(runtime_params_split)

        runtime_params = {
            "random_subset_size": runtime_params_split[0],
            "config_path": runtime_params_split[1],
            "output_dir": runtime_params_split[2],
            "massings_paths": runtime_params_split[3],
        }

        context.update(runtime_params)

    save_context(tmp_dir, context)
    save_data(tmp_dir, input.job_id)
    shutil.rmtree(tmp_dir)

    return {}


def generate_blender_command(command: str, opts: str) -> str:
    return f'blender --python-exit-code 1 --background --python blender_scripts/{command} -- {opts} --config {{config_path}}'


@queue.task(typing=True)
def stage_0(raw_input: dict) -> dict:
    logger.info("Running stage_0")

    input = AnyStageInput(**raw_input)

    tmp_dir = get_tmp_dir(input.job_id)
    load_data(tmp_dir, input.job_id)
    context = load_context(tmp_dir)

    context["preprocessed_massings_path"] = os.path.join(context["output_dir"], context["config_filename"], "00_preprocessed_massings")

    result = run_docker_command(
        context,
        generate_blender_command(
            'preprocess_input.py',
            '-i {massings_paths} -w /workdir/ -o {preprocessed_massings_path} --random_subset_size {random_subset_size}',
        )
    )
    logger.info(f"{result=}")

    save_context(tmp_dir, context)
    save_data(tmp_dir, input.job_id)
    shutil.rmtree(tmp_dir)

    return {}


@queue.task(typing=True)
def stage_1(raw_input: dict) -> dict:
    input = AnyStageInput(**raw_input)

    tmp_dir = get_tmp_dir(input.job_id)
    load_data(tmp_dir, input.job_id)
    context = load_context(tmp_dir)

    context["prior_renders_path"] = os.path.join(context["output_dir"], context["config_filename"], "01_priors")

    result = run_docker_command(
        context,
        generate_blender_command(
            'render_priors.py',
            '/workdir/{preprocessed_massings_path} /workdir/{prior_renders_path}',
        )
    )
    print(f"{result=}")

    save_context(tmp_dir, context)
    save_data(tmp_dir, input.job_id)
    shutil.rmtree(tmp_dir)

    return {}


@queue.task(typing=True)
def stage_7(raw_input: dict) -> dict:
    input = AnyStageInput(**raw_input)

    tmp_dir = get_tmp_dir(input.job_id)
    load_data(tmp_dir, input.job_id)
    context = load_context(tmp_dir)

    context["displacement_output"] = os.path.join(context["output_dir"], context["config_filename"], "07_displacement")

    result = run_docker_command(
        context,
        generate_blender_command(
            'make_displacement_map.py',
            '/workdir/{preprocessed_massings_path} /workdir/{prior_renders_path} /workdir/{generated_textures_path}/ /workdir/{displacement_output}',
        )
    )
    print(f"{result=}")

    save_context(tmp_dir, context)
    save_data(tmp_dir, input.job_id)
    shutil.rmtree(tmp_dir)

    return {}


@queue.task(typing=True)
def stage_8(raw_input: dict) -> dict:
    input = AnyStageInput(**raw_input)

    tmp_dir = get_tmp_dir(input.job_id)
    load_data(tmp_dir, input.job_id)
    context = load_context(tmp_dir)

    context["final_path"] = os.path.join(context["output_dir"], context["config_filename"], "08_final_blend")

    result = run_docker_command(
        context,
        generate_blender_command(
            'apply_textures.py',
            '/workdir/{preprocessed_massings_path} /workdir/{prior_renders_path} /workdir/{generated_textures_path} /workdir/{displacement_output}/ /workdir/{final_path}',
        )
    )
    print(f"{result=}")

    save_context(tmp_dir, context)
    save_data(tmp_dir, input.job_id)
    shutil.rmtree(tmp_dir)

    return {}
