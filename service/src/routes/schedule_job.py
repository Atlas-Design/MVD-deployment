from typing import List, Union, Callable

from typing_extensions import Protocol
from dataclasses import dataclass

import os
import json
import uuid
import time
from itertools import chain

from fastapi import APIRouter, Form, File, UploadFile, Depends, Request
from sse_starlette import EventSourceResponse

from google.cloud import batch_v1
from google.cloud import storage

from database import Job
from settings import settings

client_batch = batch_v1.BatchServiceClient()
client_storage = storage.Client()

router = APIRouter()


class CommandsCallableProtocol(Protocol):
    def __call__(self, **kwargs: dict) -> str:
        ...


class GenerateCommandsCallableProtocol(Protocol):
    def __call__(self, **kwargs: dict) -> dict:
        ...


@dataclass
class PipelineCommand:
    name: str

    image: str
    machine_type: str

    commands: List[str | CommandsCallableProtocol]

    needs_gpu: bool = False
    generate_params: Union[List[Callable[[dict], dict]], None] = None

    def image_uri(self) -> str:
        return f"europe-central2-docker.pkg.dev/unitydiffusion/sd-experiments/{self.image}"

    def generate_params_dict(self, **kwargs: dict) -> dict:
        if self.generate_params is None:
            return {}

        params = {}
        for generate_params_fn in self.generate_params:
            params.update(generate_params_fn(**kwargs))

        return params

    def generate_commands(self, **kwargs) -> List[str]:
        commands: List[str] = []

        for command in self.commands:
            if callable(command):
                commands.append(command(**kwargs))
            elif isinstance(command, str):
                commands.append(command.format(**kwargs))

        return commands


def gen_run_blender_step_command(command: str, opts: str) -> str:
    return f'blender --python-exit-code 1 --background --python blender_scripts/{command} -- {opts} --config {{config_path}}'


def gen_generate_config_command(config: "RunConfig", **kwargs: dict) -> str:
    generate_config_args = [
        '--workdir', f'/workdir/gcp/output',

        '--pos_prompt', f"'{config.pos_prompt}'",
        '--neg_prompt', f"'{config.neg_prompt}'",
        '--prompt_strength', str(config.prompt_strength),
        '--random_seed', str(config.random_seed),

        *['--disable_displacement' if config.disable_displacement else ''],

        '--texture_resolution', str(config.texture_resolution),
        '--generation_size_multiplier', str(config.generation_size_multiplier),
        '--input_mesh', f'/workdir/gcp/job_input/input_mesh.obj',
        *list(chain.from_iterable([['--style_images_paths', f'{path}'] for path in config.style_images_paths])),
        *list(chain.from_iterable(
            [['--style_images_weights', f'{weight}'] for weight in config.style_images_weights])),
        '--shadeless_strength', str(config.shadeless_strength),
        *list(chain.from_iterable([['--loras', f'{lora}'] for lora in config.loras])),
        *list(chain.from_iterable([['--loras_weights', f'{weight}'] for weight in config.loras_weights])),
    ]

    return \
        f"${{BLENDERPY}} tools/config_generator.py {' '.join(generate_config_args)} | awk '" \
        "{" \
        '   printf("random_subset_size=%s\\n", $2);' \
        '   printf("config_path=%s\\n", $3);' \
        '   printf("output_dir=%s\\n", $4);' \
        '   printf("massings_paths=");' \
        '   for (i = 5; i <= NF; i++) {' \
        '       if (i == NF) {' \
        '           printf("%s", $i);' \
        '       } else {' \
        '           printf("%s ", $i);' \
        '       }' \
        '   }' \
        '   printf("\\n");' \
        '}' \
        "' > /workdir/gcp/runtime_params"


commands: List[PipelineCommand] = [
    PipelineCommand(
        name="PRESTAGE 0 -- generate config",
        image="sd_blender",
        machine_type="e2-standard-2",
        commands=[
            gen_generate_config_command
        ]
    ),
    PipelineCommand(
        name="STAGE 0 -- preprocess massings",
        image="sd_blender",
        machine_type="e2-standard-2",
        generate_params=[
            lambda output_dir, config_filename, **kwargs: {
                "preprocessed_massings_path": os.path.join(output_dir, config_filename, "00_preprocessed_massings")
            }
        ],
        commands=[
            gen_run_blender_step_command(
                "preprocess_input.py",
                "-i $massings_paths -w /workdir/ -o {preprocessed_massings_path} --random_subset_size $random_subset_size"
            ),

        ],
    ),
    PipelineCommand(
        name="STAGE 1 -- priors rendering",
        image="sd_blender",
        machine_type="e2-standard-2",
        generate_params=[
            lambda output_dir, config_filename, **kwargs: {
                "prior_renders_path": os.path.join(output_dir, config_filename, "01_priors"),
            }
        ],
        commands=[
            gen_run_blender_step_command(
                "render_priors.py",
                "/workdir/{preprocessed_massings_path} /workdir/{prior_renders_path}"
            ),
        ],
    ),
    PipelineCommand(
        name="STAGE 2 -- texture generation",
        image="sd_comfywr",
        machine_type="n1-standard-2",
        generate_params=[
            lambda output_dir, config_filename, **kwargs: {
                "generated_textures_path": os.path.join(output_dir, config_filename, "02_gen_textures"),
            }
        ],
        commands=[
            'python3 /workdir/sd_scripts/generate_textures.py '
            '/workdir/{prior_renders_path} '
            '/workdir/{generated_textures_path} '
            '--config /workdir/{config_path} ',
        ],
        needs_gpu=True,
    ),
    # PipelineCommand(
    #     name="STAGE 3 --",
    # ),
    # PipelineCommand(
    #     name="STAGE 4 -- building semantics maps",
    #     image="sd_blender",
    #     machine_type="e2-standard-2",
    #     generate_params=[
    #         lambda output_dir, config_filename, **kwargs: {
    #             "semantics_output_dir": os.path.join(output_dir, config_filename, "04_semantics"),
    #         }
    #     ],
    #     commands=[
    #         gen_run_blender_step_command(
    #             "generate_semantics.py",
    #             "/workdir/{preprocessed_massings_path} /workdir/{prior_renders_path} /workdir/{generated_textures_path}/ /workdir/{semantics_output_dir}"
    #         ),
    #
    #     ],
    # ),
    # PipelineCommand(
    #     name="STAGE 5 -- building input semantics refinement",
    #     image="sd_blender",
    #     machine_type="e2-standard-2",
    #     generate_params=[
    #         lambda output_dir, config_filename, **kwargs: {
    #             "refinement_output_dir": os.path.join(output_dir, config_filename, "05_refinement"),
    #         }
    #     ],
    #     commands=[
    #         gen_run_blender_step_command(
    #             "refine_input_semantics.py",
    #             "/workdir/{preprocessed_massings_path} /workdir/{prior_renders_path} /workdir/{generated_textures_path}/ /workdir/{refinement_output_dir}"
    #         ),
    #     ],
    # ),
    # PipelineCommand(
    #     name="STAGE 6 -- all flat surfaces recursive grid",
    #     image="sd_blender",
    #     machine_type="e2-standard-2",
    #     generate_params=[
    #         lambda output_dir, config_filename, **kwargs: {
    #             "total_grid_output_dir": os.path.join(output_dir, config_filename, "06_total_grid"),
    #         }
    #     ],
    #     commands=[
    #         gen_run_blender_step_command(
    #             "make_total_recursive_grid.py",
    #             "/workdir/{preprocessed_massings_path} /workdir/{prior_renders_path} /workdir/{generated_textures_path}/ /workdir/{total_grid_output_dir}"
    #         ),
    #     ],
    # ),
    PipelineCommand(
        name="STAGE 7 -- displacement map",
        image="sd_blender",
        machine_type="e2-standard-2",
        generate_params=[
            lambda output_dir, config_filename, **kwargs: {
                "displacement_output": os.path.join(output_dir, config_filename, "07_displacement"),
            }
        ],
        commands=[
            gen_run_blender_step_command(
                "make_displacement_map.py",
                "/workdir/{preprocessed_massings_path} /workdir/{prior_renders_path} /workdir/{generated_textures_path}/ /workdir/{displacement_output}"
            )
        ]
    ),
    PipelineCommand(
        name="STAGE 8 -- make final blend",
        image="sd_blender",
        machine_type="e2-standard-2",
        generate_params=[
            lambda output_dir, config_filename, **kwargs: {
                "final_path": os.path.join(output_dir, config_filename, "08_final_blend"),
            }
        ],
        commands=[
            gen_run_blender_step_command(
                "apply_textures.py",
                "/workdir/{preprocessed_massings_path} /workdir/{prior_renders_path} /workdir/{generated_textures_path} /workdir/{displacement_output}/ /workdir/{final_path}"
            )
        ]
    ),
    PipelineCommand(
        name="POSTSTAGE 0 -- collect outputs",
        image="zip",
        machine_type="e2-standard-2",
        commands=[
            "cd /workdir/{output_dir}",
            "zip -r ../output.zip ."
        ]
    )
]


@dataclass
class RunConfig:
    pos_prompt: str = Form()
    neg_prompt: str = Form()
    prompt_strength: float = Form()
    random_seed: float = Form()
    disable_displacement: bool = Form()
    texture_resolution: int = Form()
    generation_size_multiplier: float = Form()
    input_mesh: UploadFile = File()
    style_images_paths: List[str] = Form([])
    style_images_weights: List[float] = Form([])
    shadeless_strength: float = Form()
    loras: List[str] = Form([])
    loras_weights: List[float] = Form([])


def split_commands_into_image_chunks(commands: List[PipelineCommand]) -> List[List[PipelineCommand]]:
    result: List[List[PipelineCommand]] = []
    chunk: List[PipelineCommand] = []

    for command in commands:
        last_command = next(iter(chunk), None)
        if last_command is None:
            chunk.append(command)
        elif last_command.machine_type == command.machine_type and last_command.needs_gpu == command.needs_gpu:
            chunk.append(command)
        else:
            result.append(chunk)
            chunk = [command]

    if len(chunk) > 0:
        result.append(chunk)

    return result


@router.post("/schedule_job")
def schedule_job(
        request: Request,
        config: RunConfig = Depends(),
):
    job_id = str(uuid.uuid4())

    data_bucket = client_storage.bucket(settings.SD_DATA_STORAGE_BUCKET_NAME)

    mesh_blob = data_bucket.blob(f"{job_id}/job_input/input_mesh.obj")
    mesh_blob.upload_from_file(config.input_mesh.file)

    runtime_params_blob = data_bucket.blob(f"{job_id}/runtime_params")
    runtime_params_blob.upload_from_string("")

    command_params = {
        "config": config,
        "gcp_dir": "gcp",
        "output_dir": "gcp/output",
        "config_path": "gcp/output/generated_config.py",
        "config_filename": "generated_config",
    }

    for command in commands:
        command_params.update(command.generate_params_dict(**command_params))

    print(f"{command_params=}")

    for command in commands:
        print(command.generate_commands(**command_params))

    # todo: split commands into incompatible "chunks" (image changed, gpu required)
    command_chunks = split_commands_into_image_chunks(commands)

    create_job_requests: list[dict] = []
    for index, chunk in enumerate(command_chunks):
        image_name = chunk[0].image
        needs_gpu = chunk[0].needs_gpu

        machine_type = chunk[0].machine_type

        if image_name == "sd_blender":
            size_gb = 50
            disk_image = "projects/unitydiffusion/global/images/sd-blender-preload-batch-cos-stable-official-20240306-00-p00"
        elif image_name == "sd_comfywr":
            size_gb = 80
            disk_image = "projects/unitydiffusion/global/images/sd-comfywr-preload-batch-cos-stable-official-20240306-00-p00"
        elif image_name == "zip":
            size_gb = 30
            disk_image = "batch-cos"
        else:
            raise ValueError(f"Unsupported image '{image_name}'")

        create_job_request = {
            "parent": "projects/unitydiffusion/locations/europe-central2",
            "job_id": f"sd-experiment-{job_id}-{index}",
            "job": {
                "task_groups": [
                    {
                        "task_spec": {
                            "volumes": [
                                {
                                    "mount_path": "/mnt/disks/share",
                                    "gcs": {
                                        "remote_path": f"{settings.SD_DATA_STORAGE_BUCKET_NAME}/{job_id}/"
                                    },
                                }
                            ],
                            "runnables": [
                                {
                                    "environment": {
                                        "variables": {
                                            "OPENCV_IO_ENABLE_OPENEXR": "1"
                                        }
                                    },
                                    "container": {
                                        "image_uri": command.image_uri(),
                                        "commands": [
                                            "bash", "-x", "-e", "-c",
                                            ' && '.join([
                                                'source /workdir/gcp/runtime_params',
                                                f"echo 'Running \"{command.name}\"'",
                                                *command.generate_commands(**command_params),
                                                f"echo 'Finished \"{command.name}\"'",
                                            ]),
                                        ],
                                        "volumes": [
                                            "/mnt/disks/share:/workdir/gcp"
                                        ],
                                    }
                                }
                                for command in chunk
                            ]
                        },
                        "task_count": 1,
                        "parallelism": 1,
                        "scheduling_policy": "IN_ORDER",
                    }
                ],
                "allocation_policy": {
                    "instances": [
                        {
                            "install_gpu_drivers": needs_gpu,
                            "policy": {
                                "provisioning_model": "STANDARD",
                                "machine_type": machine_type,
                                "accelerators": [
                                    {
                                        "type_": "nvidia-tesla-t4",
                                        "count": 1,
                                    }
                                ] if needs_gpu else [],
                                "boot_disk": {
                                    "type_": "pd-balanced",
                                    "size_gb": size_gb,
                                    "image": disk_image,
                                }
                            }
                        }
                    ]
                },
                "logs_policy": {
                    "destination": "CLOUD_LOGGING"
                },
                "labels": {
                    "job_id": str(job_id),
                    "index": str(index),
                }
            },
        }

        create_job_requests.append(create_job_request)

    job: Job = Job.create(
        id=job_id,
        total=len(create_job_requests),
        steps=json.dumps(create_job_requests),
    )

    return {"job_id": job.id}

    # current_request_index = 0
    # current_request = create_job_requests[current_request_index]

    # client_batch.create_job(batch_v1.CreateJobRequest(current_request))
    #
    # async def sse_responder():
    #     nonlocal current_request_index
    #     nonlocal current_request
    #
    #     yield {
    #         'event': 'JOB_SUBMITTED',
    #         "data": json.dumps({
    #             'job_id': job_id,
    #         }),
    #     }
    #
    #     while True:
    #         time.sleep(5)
    #
    #         if await request.is_disconnected():
    #             break
    #
    #         job_name = f"{current_request['parent']}/jobs/{current_request['job_id']}"
    #
    #         get_request = batch_v1.GetJobRequest({
    #             "name": job_name
    #         })
    #
    #         current_job_info = client_batch.get_job(get_request)
    #         current_job_state = current_job_info.status.state
    #
    #         if current_job_state == batch_v1.JobStatus.State.FAILED:
    #             yield {
    #                 'event': 'JOB_FAILURE',
    #                 "data": json.dumps({
    #                     # 'status': current_job_state,
    #                     'progress': [current_request_index, len(create_job_requests)]
    #                 })
    #             }
    #             break
    #         elif current_job_state == batch_v1.JobStatus.State.SUCCEEDED:
    #             current_request_index += 1
    #             if current_request_index >= len(create_job_requests):
    #                 yield {
    #                     'event': 'JOB_COMPLETE',
    #                     "data": json.dumps({
    #                         'job_id': job_id
    #                     })
    #                 }
    #                 break
    #
    #             current_request = create_job_requests[current_request_index]
    #             new_job = client_batch.create_job(batch_v1.CreateJobRequest(current_request))
    #
    #             yield {
    #                 'event': 'JOB_PROGRESS',
    #                 "data": json.dumps({
    #                     'status': new_job.status.state.name,
    #                     'progress': [current_request_index, len(create_job_requests)]
    #                 })
    #             }
    #         else:
    #             yield {
    #                 'event': 'JOB_PROGRESS',
    #                 "data": json.dumps({
    #                     'status': current_job_state.name,
    #                     'progress': [current_request_index, len(create_job_requests)]
    #                 })
    #             }
    #
    # return EventSourceResponse(sse_responder())
