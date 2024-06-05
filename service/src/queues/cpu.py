import time
from typing import List
from dataclasses import dataclass

import os
import shutil
from itertools import chain

from celery import Celery

from settings import settings
from queues.base import AnyStageInput, get_tmp_dir, save_context, load_context, load_data, save_data, wait_docker_exit, \
    run_blender_docker_command, generate_blender_command

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


class PreStage0Input(AnyStageInput):
    pos_prompt: str
    neg_prompt: str
    prompt_strength: float
    random_seed: int
    disable_displacement: bool
    texture_resolution: int
    input_meshes: List[str]
    style_images_paths: List[str]
    style_images_weights: List[float]
    shadeless_strength: float
    loras: List[str]
    loras_weights: List[float]

    stages_steps: List[int]

    disable_3d: bool

    apply_displacement_to_mesh: bool
    direct_config_override: List[str]

    stages_denoise: List[float]
    displacement_quality: int

    stages_upscale: List[float]
    displacement_rgb_derivation_weight: float
    enable_4x_upscale: bool
    enable_semantics: bool
    displacement_strength: float

    n_cameras: int
    camera_pitches: list[float]
    camera_yaws: list[float]

    total_remesh_mode: str
    stages_enable: List[int]


@queue.task(typing=True)
def prestage_0(raw_input: dict) -> dict:
    logger.info("Running prestage_0")

    input = PreStage0Input.parse_obj(raw_input)

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

    def multivalue_option(name: str, values: List[str]) -> List[str]:
        return [name, *values] if len(values) > 0 else []

    generate_config_args = [
        '--workdir', "{docker_output_dir}",

        '--pos_prompt', f"'{pos_prompt}'",
        '--neg_prompt', f"'{neg_prompt}'",
        '--prompt_strength', str(input.prompt_strength),
        '--random_seed', str(input.random_seed),

        *['--disable_displacement' if input.disable_displacement else ''],

        '--texture_resolution', str(input.texture_resolution),

        *multivalue_option('--input_meshes', [os.path.join(context["docker_input_dir"], path) for path in input.input_meshes]),

        *multivalue_option('--style_images_paths', [os.path.join(context["docker_input_dir"], "style_images", path) for path in input.style_images_paths]),
        *multivalue_option('--style_images_weights', [str(weight) for weight in input.style_images_weights]),

        '--shadeless_strength', str(input.shadeless_strength),

        *multivalue_option('--loras', input.loras),
        *multivalue_option('--loras_weights', [str(weight) for weight in input.loras_weights]),

        *multivalue_option('--stages_steps', [str(value) for value in input.stages_steps]),

        *['--disable_3d' if input.disable_3d else ''],
        *multivalue_option('--stages_enable', [str(value) for value in input.stages_enable]),

        *['--apply_displacement_to_mesh' if input.apply_displacement_to_mesh else ''],

        *multivalue_option('--direct_config_override', input.direct_config_override),

        *multivalue_option('--stages_denoise', [str(value) for value in input.stages_denoise]),

        '--displacement_quality', str(input.displacement_quality),

        *multivalue_option('--stages_upscale', [str(value) for value in input.stages_upscale]),

        '--displacement_strength', str(input.displacement_strength),
        '--displacement_rgb_derivation_weight', str(input.displacement_rgb_derivation_weight),

        *['--enable_4x_upscale' if input.enable_4x_upscale else ''],
        *['--enable_semantics' if input.enable_semantics else ''],

        '--n_cameras', str(input.n_cameras),
        *multivalue_option('--camera_pitches', [str(value) for value in input.camera_pitches]),
        *multivalue_option('--camera_yaws', [str(value) for value in input.camera_yaws]),

        '--total_remesh_mode', input.total_remesh_mode,
    ]

    load_data(tmp_dir, input.job_id)

    logs = wait_docker_exit(
        run_blender_docker_command(
            context,
            ' '.join([
                "${{BLENDERPY}}", "/workdir/tools/config_generator.py",
                *generate_config_args
            ]) + " > /workdir/job/output/runtime_params_raw"
        )
    )
    logger.info(f"{logs=}")

    with open(os.path.join(context["local_output_dir"], 'runtime_params_raw'), 'r') as runtime_params_raw_file:
        runtime_params_raw = runtime_params_raw_file.readline().rstrip()

        runtime_params_split = runtime_params_raw.split(' ')[1:]

        logger.info(runtime_params_split)

        runtime_params = {
            "random_subset_size": runtime_params_split[0],
            "config_path": runtime_params_split[1],
            "output_dir": runtime_params_split[2],
            "massings_paths": runtime_params_split[3],
        }

        context.update(runtime_params)

    context["preprocessed_massings_path"] = os.path.join(context["output_dir"], context["config_filename"], "00_preprocessed_massings")
    context["prior_renders_path"] = os.path.join(context["output_dir"], context["config_filename"], "01_priors")
    context["generated_textures_path"] = os.path.join(context["output_dir"], context["config_filename"], "02_gen_textures")
    context["semantics_output_dir"] = os.path.join(context["output_dir"], context["config_filename"], "04_semantics")
    context["projection_output"] = os.path.join(context["output_dir"], context["config_filename"], "03_projection")
    context["refinement_output_dir"] = os.path.join(context["output_dir"], context["config_filename"], "05_refinement")
    context["total_grid_output_dir"] = os.path.join(context["output_dir"], context["config_filename"], "06_total_grid")
    context["displacement_output"] = os.path.join(context["output_dir"], context["config_filename"], "07_displacement")
    context["upscaled_textures_path"] = os.path.join(context["output_dir"], context["config_filename"], "08_upscale")
    context["final_path"] = os.path.join(context["output_dir"], context["config_filename"], "09_final_blend")

    context["final_render"] = os.path.join(context["output_dir"], context["config_filename"], "99_final_render")

    save_context(tmp_dir, context)
    save_data(tmp_dir, input.job_id)
    shutil.rmtree(tmp_dir)

    return {}


@queue.task(typing=True)
def stage_0(raw_input: dict) -> dict:
    logger.info("Running stage_0")

    input = AnyStageInput.parse_obj(raw_input)

    tmp_dir = get_tmp_dir(input.job_id)
    load_data(tmp_dir, input.job_id)
    context = load_context(tmp_dir)

    logs = wait_docker_exit(
        run_blender_docker_command(
            context,
            generate_blender_command(
                'preprocess_input.py',
                '-i {massings_paths} -w /workdir/ -o {preprocessed_massings_path} --random_subset_size {random_subset_size}',
            )
        )
    )
    logger.info(f"{logs=}")

    save_context(tmp_dir, context)
    save_data(tmp_dir, input.job_id)
    shutil.rmtree(tmp_dir)

    return {}


@queue.task(typing=True)
def stage_1(raw_input: dict) -> dict:
    input = AnyStageInput.parse_obj(raw_input)

    tmp_dir = get_tmp_dir(input.job_id)
    load_data(tmp_dir, input.job_id)
    context = load_context(tmp_dir)


    logs = wait_docker_exit(
        run_blender_docker_command(
            context,
            generate_blender_command(
                'render_priors.py',
                '/workdir/{preprocessed_massings_path} /workdir/{prior_renders_path}',
            )
        )
    )
    logger.info(f"{logs=}")

    save_context(tmp_dir, context)
    save_data(tmp_dir, input.job_id)
    shutil.rmtree(tmp_dir)

    return {}


@queue.task(typing=True)
def stage_3(raw_input: dict) -> dict:
    input = AnyStageInput.parse_obj(raw_input)

    tmp_dir = get_tmp_dir(input.job_id)
    load_data(tmp_dir, input.job_id)
    context = load_context(tmp_dir)

    logs = wait_docker_exit(
        run_blender_docker_command(
            context,
            generate_blender_command(
                'make_projected_rgb.py',
                '/workdir/{preprocessed_massings_path} /workdir/{prior_renders_path} '
                '/workdir/{generated_textures_path}/ /workdir/{projection_output}',
            )
        )
    )
    logger.info(f"{logs=}")

    save_context(tmp_dir, context)
    save_data(tmp_dir, input.job_id)
    # shutil.rmtree(tmp_dir)

    return {}


# @queue.task(typing=True)
# def stage_5(raw_input: dict) -> dict:
#     input = AnyStageInput.parse_obj(raw_input)
#
#     tmp_dir = get_tmp_dir(input.job_id)
#     load_data(tmp_dir, input.job_id)
#     context = load_context(tmp_dir)
#
#
#     logs = wait_docker_exit(
#         run_blender_docker_command(
#             context,
#             generate_blender_command(
#                 'refine_input_semantics.py',
#                 '/workdir/{preprocessed_massings_path} /workdir/{prior_renders_path} '
#                 '/workdir/{generated_textures_path}/ /workdir/{refinement_output_dir}',
#             )
#         )
#     )
#     logger.info(f"{logs=}")
#
#     save_context(tmp_dir, context)
#     save_data(tmp_dir, input.job_id)
#     shutil.rmtree(tmp_dir)
#
#     return {}


@queue.task(typing=True)
def stage_6(raw_input: dict) -> dict:
    input = AnyStageInput.parse_obj(raw_input)

    tmp_dir = get_tmp_dir(input.job_id)
    load_data(tmp_dir, input.job_id)
    context = load_context(tmp_dir)

    logs = wait_docker_exit(
        run_blender_docker_command(
            context,
            generate_blender_command(
                'make_total_recursive_grid.py',
                '/workdir/{preprocessed_massings_path} /workdir/{prior_renders_path} '
                '/workdir/{generated_textures_path}/ /workdir/{total_grid_output_dir}',
            )
        )
    )
    logger.info(f"{logs=}")

    save_context(tmp_dir, context)
    save_data(tmp_dir, input.job_id)
    # shutil.rmtree(tmp_dir)

    return {}


@queue.task(typing=True)
def stage_7(raw_input: dict) -> dict:
    input = AnyStageInput.parse_obj(raw_input)

    tmp_dir = get_tmp_dir(input.job_id)
    load_data(tmp_dir, input.job_id)
    context = load_context(tmp_dir)

    logs = wait_docker_exit(
        run_blender_docker_command(
            context,
            generate_blender_command(
                'make_displacement_map.py',
                '/workdir/{preprocessed_massings_path} /workdir/{prior_renders_path} '
                '/workdir/{generated_textures_path}/ /workdir/{displacement_output}',
            )
        )
    )
    logger.info(f"{logs=}")

    save_context(tmp_dir, context)
    save_data(tmp_dir, input.job_id)
    # shutil.rmtree(tmp_dir)

    return {}


@queue.task(typing=True)
def stage_9(raw_input: dict) -> dict:
    input = AnyStageInput.parse_obj(raw_input)

    tmp_dir = get_tmp_dir(input.job_id)
    load_data(tmp_dir, input.job_id)
    context = load_context(tmp_dir)

    logs = wait_docker_exit(
        run_blender_docker_command(
            context,
            generate_blender_command(
                'make_final_blend.py',
                '/workdir/{preprocessed_massings_path} /workdir/{prior_renders_path} '
                '/workdir/{generated_textures_path} /workdir/{projection_output} /workdir/{displacement_output}/ '
                '/workdir/{upscaled_textures_path} /workdir/{final_path}',
            )
        )
    )
    logger.info(f"{logs=}")

    save_context(tmp_dir, context)
    save_data(tmp_dir, input.job_id)
    # shutil.rmtree(tmp_dir)

    return {}
