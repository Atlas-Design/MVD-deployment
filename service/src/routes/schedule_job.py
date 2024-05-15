import shutil
import pathlib
import tempfile
from typing import List

from dataclasses import dataclass

import os
import math
import json
import uuid

from fastapi import APIRouter, Form, File, UploadFile, Depends, Request

from google.cloud import storage

import queues.cpu
from database import Job
from queues.base import save_data

client_storage = storage.Client()

router = APIRouter()


@dataclass
class RunConfig:
    pos_prompt: str = Form()
    neg_prompt: str = Form()
    prompt_strength: float = Form()
    random_seed: float = Form()
    disable_displacement: bool = Form()
    texture_resolution: int = Form()
    input_meshes: List[UploadFile] = File()
    style_images: List[UploadFile] = File(default=[])
    style_images_weights: List[float] = Form(default=[])
    shadeless_strength: float = Form()
    loras: List[str] = Form(default=[])
    loras_weights: List[float] = Form(default=[])

    stage_1_steps: int = Form(default=32)
    stage_2_steps: int = Form(default=20)

    disable_3d: bool = Form(default=False)
    disable_upscaling: bool = Form(default=False)

    organic: bool = Form(default=False)
    apply_displacement_to_mesh: bool = Form(default=False)
    direct_config_override: str = Form(default="")

    stage_2_denoise: float = Form(default=0.45)
    displacement_quality: int = Form(default=2)

    stage_2_upscale: float = Form(default=1.9)
    displacement_rgb_derivation_weight: float = Form(default=0.0)
    enable_4x_upscale: bool = Form(default=False)
    enable_semantics: bool = Form(default=False)
    displacement_strength: float = Form(default=0.03)

    n_cameras: int = Form(default=4)
    camera_pitches: List[float] = Form(default=[math.pi / 2.5])
    camera_yaws: List[float] = Form(default=[0.0])


@router.post("/schedule_job")
def schedule_job(
        config: RunConfig = Depends(),
):
    job_id = str(uuid.uuid4())

    input_meshes = [(f'{i:0>3}_{file.filename}', file) for i, file in enumerate(config.input_meshes)]
    style_images = [(f'{i:0>3}_{file.filename}', file) for i, file in enumerate(config.style_images)]

    with tempfile.TemporaryDirectory() as tmpdir:
        job_input_dir = os.path.join(tmpdir, 'job', 'input')
        os.makedirs(job_input_dir, exist_ok=True)
        for filename, input_mesh in input_meshes:
            with open(os.path.join(job_input_dir, filename), 'wb') as f:
                shutil.copyfileobj(input_mesh.file, f)

        style_images_dir = os.path.join(job_input_dir, 'style_images')
        os.makedirs(style_images_dir, exist_ok=True)
        for filename, style_file in style_images:
            with open(os.path.join(style_images_dir, filename), 'wb') as f:
                shutil.copyfileobj(style_file.file, f)

        save_data(tmpdir, job_id)

    steps = list(filter(
        lambda x: x is not None,
        [
            'cpu.prestage_0',
            'cpu.stage_0',
            'cpu.stage_1',
            'gpu.stage_2',

            *['cpu.stage_3' if not config.disable_3d else None],
            *['gpu.stage_4' if config.enable_semantics else None],

            *['cpu.stage_7' if not config.disable_displacement else None],
            *['gpu.stage_8' if config.enable_4x_upscale and not config.disable_3d else None],
            *['cpu.stage_9' if not config.disable_3d else None],

            # 'gpu.poststage_0',
        ]
    ))

    job: Job = Job.create(
        id=job_id,
        total=len(steps),
        steps=json.dumps(steps),
        payload=json.dumps(queues.cpu.PreStage0Input(
            job_id=job_id,

            pos_prompt=config.pos_prompt,
            neg_prompt=config.neg_prompt,
            prompt_strength=config.prompt_strength,
            random_seed=config.random_seed,
            disable_displacement=config.disable_displacement,
            texture_resolution=config.texture_resolution,
            input_meshes=[filename for filename, _ in input_meshes],
            style_images_paths=[filename for filename, _ in style_images],
            style_images_weights=config.style_images_weights,
            shadeless_strength=config.shadeless_strength,
            loras=config.loras,
            loras_weights=config.loras_weights,

            stage_1_steps=config.stage_1_steps,
            stage_2_steps=config.stage_2_steps,
            disable_3d=config.disable_3d,
            disable_upscaling=config.disable_upscaling,

            organic=config.organic,
            apply_displacement_to_mesh=config.apply_displacement_to_mesh,
            direct_config_override=config.direct_config_override,

            stage_2_denoise=config.stage_2_denoise,
            displacement_quality=config.displacement_quality,

            stage_2_upscale=config.stage_2_upscale,

            displacement_rgb_derivation_weight=config.displacement_rgb_derivation_weight,
            enable_4x_upscale=config.enable_4x_upscale,
            enable_semantics=config.enable_semantics,
            displacement_strength=config.displacement_strength,

            n_cameras=config.n_cameras,
            camera_pitches=config.camera_pitches,
            camera_yaws=config.camera_yaws,
        ).model_dump()),
    )

    return {"job_id": job.id}
