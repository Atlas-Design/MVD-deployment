import shutil
import tempfile
from typing import List

from dataclasses import dataclass

import os
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
    generation_size_multiplier: float = Form()
    input_mesh: UploadFile = File()
    style_images: List[UploadFile] = File(default=[])
    style_images_weights: List[float] = Form(default=[])
    shadeless_strength: float = Form()
    loras: List[str] = Form(default=[])
    loras_weights: List[float] = Form(default=[])

    stage_1_steps: int = Form(default=26)
    stage_2_steps: int = Form(default=20)

    disable_3d: bool = Form(default=False)
    disable_upscaling: bool = Form(default=False)

    organic: bool = Form(default=False)
    apply_displacement_to_mesh: bool = Form(default=False)
    direct_config_override: str = Form(default="")

    stage_2_denoise: float = Form(default=0.45)
    displacement_quality: int = Form(default=2)


@router.post("/schedule_job")
def schedule_job(
        request: Request,
        config: RunConfig = Depends(),
):
    config.random_seed = int(config.random_seed)

    job_id = str(uuid.uuid4())

    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, 'job', 'input'), exist_ok=True)
        with open(os.path.join(tmpdir, 'job', 'input', 'input_mesh.obj'), 'wb') as f:
            shutil.copyfileobj(config.input_mesh.file, f)

        os.makedirs(os.path.join(tmpdir, 'job', 'input', 'style_images'), exist_ok=True)
        for style_file in config.style_images:
            with open(os.path.join(tmpdir, 'job', 'input', 'style_images', style_file.filename), 'wb') as f:
                shutil.copyfileobj(style_file.file, f)

        save_data(tmpdir, job_id)

    if config.disable_3d:
        steps = [
            'cpu.prestage_0', 'cpu.stage_0', 'cpu.stage_1',
            'gpu.stage_2'
        ]
    else:
        steps = [
            'cpu.prestage_0', 'cpu.stage_0', 'cpu.stage_1',
            'gpu.stage_2', 'cpu.stage_7', 'cpu.stage_8'
        ]

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
            generation_size_multiplier=config.generation_size_multiplier,
            style_images_paths=[si.filename for si in config.style_images],
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
        ).asdict()),
    )

    return {"job_id": job.id}
