import tempfile
import time
import zipfile
from typing import List, Optional
from dataclasses import dataclass

import math
import os.path
from urllib.request import urlretrieve

import click

from .version import __version__
from .service import ServiceScheduleJobCommand, ServiceGetDownloadUrlCommand, ServiceCheckStatusCommand

SUPPORTED_LORAS = [
    'japanese_shop_v0.1',
    'cyberpunk_v0.1',
    'prahov_v0.1',

    'ext_ghiblism',
    'ext_cyberpunk',
    'ext_buildingface',
    'ext_cyberpunk_fantasy',
    'ext_isometric',
]


@dataclass
class GlobalConfig:
    verbose: bool = False
    backend_base: str = ""


@click.group(context_settings={'show_default': True})
@click.pass_context
@click.version_option(__version__)
# @click.option("-v", "--verbose", type=bool, is_flag=True, default=False, help="Enable verbose mode")
@click.option("--backend_base", type=str, default="http://34.140.119.26:3000", help="Backend base URL")
def cli(
        ctx: click.Context,
        # verbose: bool,
        backend_base: str,
):
    ctx.ensure_object(GlobalConfig)

    # ctx.obj.verbose = verbose
    ctx.obj.backend_base = backend_base


@cli.command(short_help="Schedule a new job")
@click.pass_context
@click.option("--pos_prompt", type=str,
              default="best quality, a multi-floor building, extremely detailed, a lot of windows",
              help="A positive SD prompt to use")
@click.option("--neg_prompt", type=str, default="worst quality, bad quality, simple, wardrobe",
              help="A negative SD prompt to use")
@click.option("--prompt_strength", type=float, default=7.5,
              help="Classifier-free guidance scale. It's basically the text prompting weight.")
@click.option("--random_seed", type=int, default=42, help="Global random seed for the whole pipeline")
@click.option("--disable_displacement", is_flag=True, default=False,
              help="Don't generate displacement maps. Faster processing time.")
@click.option("--texture_resolution", type=int, default=2560,
              help="Baked UV texture resolution. Lower value is slightly lower processing time.")
@click.option("-i", "--input_meshes_path", "--input_meshes", type=click.Path(exists=True, file_okay=True, dir_okay=False),
              required=True, multiple=True,
              help="A path to the input massing .obj file.")
@click.option("-s", "--style_images_paths", type=click.Path(exists=True, file_okay=True, dir_okay=False), multiple=True,
              default=[], help="Paths to input style images that will influence the result")
@click.option("-sw", "--style_images_weights", type=float, multiple=True, default=[],
              help='Weight of influence for each style images.'
                   'Should be exactly the same count as the style_images_paths parameter.'
                   'Recommended value is around 0.3.')
@click.option("--shadeless_strength", type=float, default=0.6,
              help='Reduces amount of shadows/ambient occlusion in generated images, '
                   'making the generated textures usable as a base color without visible artifacts'
                   ' -- projected shadows')
@click.option("-l", "--loras", type=click.Choice(choices=SUPPORTED_LORAS), multiple=True, default=[],
              help='Style-specific LoRA checkpoints to use.'
                   'It is recommended to experiment with style images first.'
                   'This feature can be used independently (with or without style images).'
                   'For LoRAs starting with ext_, the trigger words are not added automatically to prompt !!!')
@click.option("-lw", "--loras_weights", type=float, multiple=True, default=[],
              help='Weight of influence for each LoRA.'
                   'Should be exactly the same count as the loras parameter.'
                   'Recommended value is around 0.5')
@click.option("-f", "--follow", is_flag=True, type=bool, default=False,
              help='When set program will wait until job completes.')
@click.option("-o", "--output", type=click.Path(file_okay=True, dir_okay=True), required=False,
              help="Path where output will be downloaded. If ends with .zip, zip archive will be downloaded, "
                   "otherwise folder with that name will be created, and output will be extracted into it."
                   "Enables --follow flag")
@click.option('--stage_1_steps', type=int, default=32,
              help="Amount of diffusion steps for generating non-upscaled multi-view image."
                   "Lower values will usually cause blurry/noisy/distorted/undetailed image."
                   "Has relatively marginal effect on processing speed unless almost everything else "
                   "possible is disabled for performance.")
@click.option('--stage_2_steps', type=int, default=20,
              help="Amount of diffusion steps for diffusion upscaled multi-view image."
                   "Only relevant if disable_displacement flag is not set."
                   "Lower values will usually cause noiser image image (in terms of details)."
                   "The lower the value, the lower the processing time.")
@click.option("--disable_3d", is_flag=True, default=False,
              help="Skip everything related to 3D, generate just the multi-view image "
                   "and it's depth if it is not disabled")
@click.option("--disable_upscaling", is_flag=True, default=False,
              help="Don't run diffusion upscaling. Much faster processing time, "
                   "blurry textures with likely less detail.")
@click.option("--organic", is_flag=True, default=False,
              help="This option strongly modify the input mesh by remeshing and smoothing it,"
                   "then it is treated on a somewhat organic way in the rest of processing steps.")
@click.option("--apply_displacement_to_mesh", is_flag=True, default=False,
              help="WARNING: enabling this flat makes the final result very large -- roughly 200-300MB."
                   "Relevant only when disable_3d and disable_displacement flags are not set."
                   "Create a very high-poly mesh with applied displacement as a blender modifier,"
                   "and material with bump mapping using the same displacement map.")
@click.option("--direct_config_override", "--dco", type=str, default="",
              help="Advanced feature. List of key=value pairs to override in the underlying generated config."
                   "Changes are applied at the end, so can also override values implicated by other CLI params")
@click.option('--stage_2_denoise', type=float, default=0.45,
              help="How much image can be changed on upscaling stage -- setting too high may cause too much"
                   " repeatable and distorted geometry to be generated, especially with high"
                   "stage_2_upscale values."
                   "Only relevant when disable_upscaling flag is not set.")
@click.option('--displacement_quality', type=int, default=2,
              help="Higher values will produce a little bit less noisy displacement,"
                   "but slow down the pipeline significantly."
                   "Only relevant when disable_displacement flag is not set."
                   "Setting beyond ~12 is not recommended as the results will likely be no better afterwards "
                   " and processing much slower")
@click.option('--displacement_rgb_derivation_weight', type=float, default=0,
              help='A value from range <0, 1> interpolating between estimated displacement'
                   'and simple adjusted grayscaled RGB image. When > 0, generated displacement will affected '
                   'by color brightness, displacing e.g. shadows or normally flat patterns.'
                   'When ==1, it speeds up pipeline because it then disables default displacement processing.')
@click.option('--enable_4x_upscale', is_flag=True, default=False,
              help="Upscale RGB and displacement (if applies) UV textures 4x. "
                   "Relevant only when disable_3d flag is not set. "
                   "Significantly slows down pipeline.")
@click.option('--enable_semantics', is_flag=True, default=False,
              help="Enable semantic segmentation output for buildings."
                   "Significantly slows down pipeline.")
@click.option('--displacement_strength', type=float, default=0.03,
              help="Simply displacement strength on the final mesh "
                   "(which is normalized so that avg. bounding box dimension size is 1)")
@click.option('--stage_2_upscale', type=float, default=1.9,
              help="Multiplier for the generated texture size. "
                   "Relevant only when disable_upscaling flag is not set. "
                   "The higher the value the slower the processing time. "
                   "Keep in mind the texture_resolution value -- "
                   "too small texture_resolution parameter value will not utilize "
                   "high stage_2_upscale properly -- "
                   "Information will be lost when projecting RGB data to UV space."
                   "Recommended to keep roughly between 1.5-2.5.")
@click.option('--n_cameras', type=int, default=4, help='Amount of projection views.')
@click.option('--camera_pitches', type=float, multiple=True, default=[math.pi / 2.5],
              help="Vertical angles from what building should be viewed "
                   "(camera looking from higher or lower angle). "
                   "Value 0 means viewing orthogonally from the top, and pi from the bottom. "
                   "There can be a single value or as many as value of --n_cameras argument."
                   "If a single value is provided other will be generated to provide a turntable object view")
@click.option('--camera_yaws', type=float, multiple=True, default=[0],
              help="Angle (rotation around the upwards axis) of the first camera view when doing projection."
                   "Depending on the input shape different values can work better"
                   "There can be a single value or as many as value of --n_cameras argument."
                   "If a single value is provided, it is repeated --n_cameras times.")
def schedule(
        ctx: click.Context,

        follow: bool,
        output: str,

        input_meshes_path: str,
        style_images_paths: List[str],

        **kwargs,
):
    if output is not None:
        follow = True

    if len(style_images_paths) != len(kwargs['style_images_weights']):
        raise click.UsageError(
            "style images and style images weights arguments should be in the same amount.",
        )

    if len(kwargs['loras']) != len(kwargs['loras_weights']):
        raise click.UsageError(
            "loras and loras_weights arguments should be in the same amount.",
        )
    if kwargs['enable_4x_upscale'] and kwargs['disable_3d']:
        raise click.UsageError(
            'Both enable_4x_upscale and disable_3d flags cannot be used together.'
        )

    if len(kwargs['camera_yaws']) not in (1, kwargs['n_cameras']):
        raise click.UsageError('Camera yaws amount needs to be either 1 or --n_cameras')
    if len(kwargs['camera_pitches']) not in (1, kwargs['n_cameras']):
        raise click.UsageError('Camera pitches amount needs to be either 1 or --n_cameras')

    global_config = ctx.find_object(GlobalConfig)
    assert (global_config is not None)

    schedule_command = ServiceScheduleJobCommand(
        base_url=global_config.backend_base,
        data={**kwargs},
        files=[
            *[("style_images", open(sip, "rb")) for sip in style_images_paths],
            *[("input_meshes", open(imp, "rb")) for imp in input_meshes_path],
        ],
    )

    schedule_result = schedule_command.run()
    job_id = schedule_result["job_id"]
    print(f"Job ID: {job_id}")

    if follow:
        check_command = ServiceCheckStatusCommand(
            base_url=global_config.backend_base,
            job_id=job_id
        )

        while True:
            time.sleep(5)

            check_result = check_command.run()

            status = check_result["status"]
            progress = check_result["progress"]

            print(f"Job ID: {job_id}\nStatus: {status}\nProgress: {progress[0]}/{progress[1]}\n")

            if status == "FAILED":
                raise click.ClickException("Job failed")
            elif status == "SUCCEEDED":
                break

    if output:
        download_result(
            ctx=ctx,
            job_id=schedule_result["job_id"],
            output=output,
        )


def download_result(
        ctx: click.Context,
        job_id: str,
        output: str,
):
    global_config = ctx.find_object(GlobalConfig)
    assert (global_config is not None)

    get_url_command = ServiceGetDownloadUrlCommand(
        base_url=global_config.backend_base,
        job_id=job_id
    )

    get_url_result = get_url_command.run()

    if output.endswith(".zip"):
        urlretrieve(get_url_result["download_url"], output)
    else:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'data.zip')

            urlretrieve(get_url_result["download_url"], path)

            with zipfile.ZipFile(path, 'r') as zf:
                os.makedirs(output, exist_ok=True)
                zf.extractall(output)


@cli.command(short_help="Download output of already finished job")
@click.pass_context
@click.option("-j", "--job-id", type=str, required=True,
              help="Job ID whose result to download")
@click.option("-o", "--output", type=click.Path(file_okay=True, dir_okay=True), required=True,
              help="Path where output will be downloaded. If ends with .zip, zip archive will be downloaded, "
                   "otherwise folder with that name will be created, and output will be extracted into it.")
def download(
        ctx: click.Context,
        job_id: str,
        output: str,
):
    global_config = ctx.find_object(GlobalConfig)
    assert (global_config is not None)

    check_command = ServiceCheckStatusCommand(
        base_url=global_config.backend_base,
        job_id=job_id
    )

    check_result = check_command.run()

    status = check_result["status"]
    if status == "FAILED":
        raise click.ClickException("Cannot download output of failed job")
    elif status != "SUCCEEDED":
        raise click.ClickException("Job is still pending, wait until job is completed")

    download_result(ctx, job_id, output)


@cli.command(short_help="Check status of job")
@click.pass_context
@click.option("-j", "--job-id", type=str, required=True,
              help="Job ID whose result to download")
@click.option("-f", "--follow", is_flag=True, type=bool, default=False,
              help='When set program will wait until job completes.')
def check_status(
        ctx: click.Context,
        job_id: str,
        follow: bool,
):
    global_config = ctx.find_object(GlobalConfig)
    assert (global_config is not None)

    check_command = ServiceCheckStatusCommand(
        base_url=global_config.backend_base,
        job_id=job_id
    )

    while True:
        check_result = check_command.run()

        status = check_result["status"]
        progress = check_result["progress"]

        print(f"Job ID: {job_id}\nStatus: {status}\nProgress: {progress[0]}/{progress[1]}\n")

        if status == "FAILED":
            raise click.ClickException("Job failed")
        elif status == "SUCCEEDED":
            break

        if not follow:
            break

        time.sleep(5)
