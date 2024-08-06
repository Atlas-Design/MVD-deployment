import docker
from celery import Celery, Task
from celery.signals import task_revoked
from celery.utils.log import get_task_logger

from settings import settings
from queues.base import AnyStageInput, get_tmp_dir, save_context, load_context, save_data, load_data, wait_docker_exit, \
    run_comfywr_docker_command, run_blender_docker_command, generate_blender_command, generate_container_name

logger = get_task_logger(__name__)

queue = Celery(
    'gpu',
    broker=settings.RABBITMQ_URL,
    backend=settings.REDIS_URL
)
queue.conf.task_default_queue = 'gpu'
queue.conf.broker_connection_retry = True
queue.conf.broker_connection_retry_on_startup = False
queue.conf.task_track_started = True


@task_revoked.connect()
def on_revoke(**kwargs):
    logger.info(f"Got revoke: {kwargs}")

    container_name = f"{kwargs['sender'].__name__}-{kwargs['request'].id}"
    client = docker.from_env()
    client.api.kill(container_name)


@queue.task(bind=True, typing=True)
def stage_2(self: Task, raw_input: dict) -> dict:
    input = AnyStageInput.model_validate(raw_input)

    tmp_dir = get_tmp_dir(input.job_id)
    load_data(tmp_dir, input.job_id)
    context = load_context(tmp_dir)

    logs = wait_docker_exit(
        run_comfywr_docker_command(
            generate_container_name(self.__name__, self.request.id),
            context,
            'python /workdir/sd_scripts/generate_textures.py '
            '/workdir/{prior_renders_path} '
            '/workdir/{generated_textures_path} '
            '--config /workdir/{config_path} ',
            with_gpu=True,
        ),
    )

    logger.info(f"{logs=}")

    save_context(tmp_dir, context)
    save_data(tmp_dir, input.job_id)
    # shutil.rmtree(tmp_dir)

    return {}


@queue.task(bind=True, typing=True)
def stage_4(self: Task, raw_input: dict) -> dict:
    input = AnyStageInput.model_validate(raw_input)

    tmp_dir = get_tmp_dir(input.job_id)
    load_data(tmp_dir, input.job_id)
    context = load_context(tmp_dir)

    logs = wait_docker_exit(
        run_blender_docker_command(
            generate_container_name(self.__name__, self.request.id),
            context,
            generate_blender_command(
                'generate_semantics.py',
                '/workdir/{preprocessed_massings_path} /workdir/{prior_renders_path} '
                '/workdir/{generated_textures_path}/ /workdir/{semantics_output_dir}'
            ),
            with_gpu=True,
        )
    )

    logger.info(f"{logs=}")

    save_context(tmp_dir, context)
    save_data(tmp_dir, input.job_id)
    # shutil.rmtree(tmp_dir)

    return {}


@queue.task(bind=True, typing=True)
def stage_7(self: Task, raw_input: dict) -> dict:
    input = AnyStageInput.model_validate(raw_input)

    tmp_dir = get_tmp_dir(input.job_id)
    load_data(tmp_dir, input.job_id)
    context = load_context(tmp_dir)

    logs = wait_docker_exit(
        run_blender_docker_command(
            generate_container_name(self.__name__, self.request.id),
            context,
            generate_blender_command(
                'make_displacement_map.py',
                '/workdir/{preprocessed_massings_path} /workdir/{prior_renders_path} '
                '/workdir/{generated_textures_path}/ /workdir/{displacement_output}',
            ),
            with_gpu=True,
        )
    )
    logger.info(f"{logs=}")

    save_context(tmp_dir, context)
    save_data(tmp_dir, input.job_id)
    # shutil.rmtree(tmp_dir)

    return {}



@queue.task(bind=True, typing=True)
def stage_8(self: Task, raw_input: dict) -> dict:
    input = AnyStageInput.model_validate(raw_input)

    tmp_dir = get_tmp_dir(input.job_id)
    load_data(tmp_dir, input.job_id)
    context = load_context(tmp_dir)

    logs = wait_docker_exit(
        run_comfywr_docker_command(
            generate_container_name(self.__name__, self.request.id),
            context,
            'python /workdir/sd_scripts/final_upscale.py '
            '/workdir/{projection_output} '
            '/workdir/{displacement_output} '
            '/workdir/{upscaled_textures_path} '
            '--config /workdir/{config_path} ',
            with_gpu=True,
        )
    )

    logger.info(f"{logs=}")

    save_context(tmp_dir, context)
    save_data(tmp_dir, input.job_id)
    # shutil.rmtree(tmp_dir)

    return {}


@queue.task(bind=True, typing=True)
def poststage_0(self: Task, raw_input: dict) -> dict:
    input = AnyStageInput.model_validate(raw_input)

    tmp_dir = get_tmp_dir(input.job_id)
    load_data(tmp_dir, input.job_id)
    context = load_context(tmp_dir)

    logs = wait_docker_exit(
        run_blender_docker_command(
            generate_container_name(self.__name__, self.request.id),
            context,
            generate_blender_command(
                'make_final_renders.py',
                '{output_dir} {final_render} -n 1 --samples 32 --render_scale 30',
                with_config=False,
            ),
            with_gpu=True,
        )
    )

    logger.info(f"{logs=}")

    save_context(tmp_dir, context)
    save_data(tmp_dir, input.job_id)
    # shutil.rmtree(tmp_dir)

    return {}
