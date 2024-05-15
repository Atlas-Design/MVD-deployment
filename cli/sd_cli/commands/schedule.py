from typing import List, Optional

import math
import time
import argparse

from pathlib import Path

from sd_cli.error import UsageError
from sd_cli.utils.download_result import download_result
from sd_cli.api.service import ServiceScheduleJobCommand, ServiceCheckStatusCommand

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


def add_subparser(subparsers):
    parser: argparse.ArgumentParser = subparsers.add_parser(
        name='schedule',
        help='Schedule a new job',
        description='Schedule a new job',
        formatter_class=argparse.MetavarTypeHelpFormatter,
    )

    parser.add_argument(
        "-f", "--follow",
        action='store_true',
        default=False,
        help='When set program will wait until job completes.'
    )

    parser.add_argument(
        "-o", "--output",
        action='store',
        type=Path,
        required=False,
        help="Path where output will be downloaded. If ends with .zip, zip archive will be downloaded, "
             "otherwise folder with that name will be created, and output will be extracted into it."
             "Enables --follow flag"
    )

    # -------- BEGIN Copy from sd_experiments --------
    def existing_file_type(path: str):
        path = Path(path)
        if not path.is_file():
            parser.error(f"File {path} doesn't exist")
        else:
            return path
    file_type = existing_file_type

    parser.add_argument('--pos_prompt', type=str,
                        default="best quality, a multi-floor building, extremely detailed, a lot of windows",
                        help='A positive SD prompt to use')
    parser.add_argument('--neg_prompt', type=str, default="worst quality, bad quality, simple, wardrobe",
                        help='A negative SD prompt to use')
    parser.add_argument('--prompt_strength', type=float, default=7.5,
                        help="Classifier-free guidance scale. It's basically the text prompting weight.")
    parser.add_argument('--random_seed', type=int, default=42,
                        help="Global random seed for the whole pipeline")
    parser.add_argument('--texture_resolution', type=int, default=2560,
                        help="Baked UV RGB and displacement textures resolution for the final mesh."
                             "Lower value is slightly lower processing time. "
                             "Only relevant if disable_3d flag is not set."
                             "When running with disable_upscaling flag, "
                             "it is safe to keep at lower value without much detail loss -- e.g. 1280."
                             "High values especially slows down pipeline when enable_semantics flag is set")
    parser.add_argument('--stage_2_upscale', type=float, default=1.9,
                        help="Multiplier for the generated texture size. "
                             "Relevant only when disable_upscaling flag is not set. "
                             "The higher the value the slower the processing time. "
                             "Keep in mind the texture_resolution value -- "
                             "too small texture_resolution parameter value will not utilize "
                             "high stage_2_upscale properly -- "
                             "Information will be lost when projecting RGB data to UV space."
                             "Recommended to keep roughly between 1.5-2.5.")
    parser.add_argument('--stage_1_steps', type=int, default=32,
                        help="Amount of diffusion steps for generating non-upscaled multi-view image."
                             "Lower values will usually cause blurry/noisy/distorted/undetailed image."
                             "Has relatively marginal effect on processing speed unless almost everything else "
                             "possible is disabled for performance.")
    parser.add_argument('--stage_2_steps', type=int, default=20,
                        help="Amount of diffusion steps for diffusion upscaled multi-view image."
                             "Only relevant if disable_displacement flag is not set."
                             "Lower values will usually cause noiser image image (in terms of details)."
                             "The lower the value, the lower the processing time.")
    parser.add_argument('--stage_2_denoise', type=float, default=0.45,
                        help="How much image can be changed on upscaling stage -- setting too high may cause too much"
                             " repeatable and distorted geometry to be generated, especially with high"
                             "stage_2_upscale values."
                             "Only relevant when disable_upscaling flag is not set.")
    parser.add_argument('--displacement_quality', type=int, default=2,
                        help="Higher values will produce a little bit less noisy displacement,"
                             "but slow down the pipeline significantly."
                             "Only relevant when disable_displacement flag is not set."
                             "Setting beyond ~12 is not recommended as the results will likely be no better afterwards "
                             " and processing much slower")
    parser.add_argument('--displacement_strength', type=float, default=0.03,
                        help="Simply displacement strength on the final mesh "
                             "(which is normalized so that avg. bounding box dimension size is 1)")
    parser.add_argument('--displacement_rgb_derivation_weight', type=float, default=0,
                        help='A value from range <0, 1> interpolating between estimated displacement'
                             'and simple adjusted grayscaled RGB image. When > 0, generated displacement will affected '
                             'by color brightness, displacing e.g. shadows or normally flat patterns.'
                             'When ==1, it speeds up pipeline because it then disables default displacement processing.')

    # Camera views setup
    parser.add_argument('--n_cameras', type=int, default=4, help='Amount of projection views.')
    parser.add_argument('--camera_pitches', type=float, nargs='+', default=[math.pi / 2.5],
                        help="Vertical angles from what building should be viewed "
                             "(camera looking from higher or lower angle). "
                             "Value 0 means viewing orthogonally from the top, and pi from the bottom. "
                             "There can be a single value or as many as value of --n_cameras argument."
                             "If a single value is provided other will be generated to provide a turntable object view")
    parser.add_argument('--camera_yaws', type=float, nargs='+', default=[0],
                        help="Angle (rotation around the upwards axis) of the first camera view when doing projection."
                             "Depending on the input shape different values can work better"
                             "There can be a single value or as many as value of --n_cameras argument."
                             "If a single value is provided, it is repeated --n_cameras times.")

    parser.add_argument('--organic', action='store_true', default=False,
                        help="This option strongly modify the input mesh by remeshing and smoothing it,"
                             "then it is treated on a somewhat organic way in the rest of processing steps.")
    parser.add_argument('--apply_displacement_to_mesh', action='store_true', default=False,
                        help="WARNING: enabling this flat makes the final result very large -- roughly 200-300MB."
                             "Relevant only when disable_3d and disable_displacement flags are not set."
                             "Create a very high-poly mesh with applied displacement as a blender modifier,"
                             "and material with bump mapping using the same displacement map.")

    parser.add_argument('--disable_3d', action='store_true', default=False,
                        help="Skip everything related to 3D, generate just the multi-view image "
                             "and it's depth if it is not disabled")
    parser.add_argument('--disable_upscaling', action='store_true', default=False,
                        help="Don't run diffusion upscaling. Much faster processing time, "
                             "blurry textures with likely less detail.")
    parser.add_argument('--disable_displacement', action='store_true', default=False,
                        help="Don't generate displacement maps. Faster processing time."
                             "In case of running disable_3d, it skips generating depth maps.")
    parser.add_argument('--enable_4x_upscale', action='store_true', default=False,
                        help="Upscale RGB and displacement (if applies) UV textures 4x. "
                             "Relevant only when disable_3d flag is not set. "
                             "Significantly slows down pipeline.")
    parser.add_argument('--enable_semantics', action='store_true', default=False,
                        help="Enable semantic segmentation output for buildings."
                             "Significantly slows down pipeline.")

    parser.add_argument('-i', '--input_meshes', type=file_type, nargs="+", required=True,
                        help='A path to the input massing .obj file.')
    parser.add_argument('-s', '--style_images_paths', type=file_type, nargs="*", default=[],
                        help='Paths to input style images that will influence the result')
    parser.add_argument('-sw', '--style_images_weights', type=float, nargs="*", default=[],
                        help='Weight of influence for each style images.'
                             'Should be exactly the same count as the style_images_paths parameter.'
                             'Recommended value is around 0.3.')

    parser.add_argument('--shadeless_strength', type=float, default=0.6,
                        help='Reduces amount of shadows/ambient occlusion in generated images, '
                             'making the generated textures usable as a base color without visible artifacts'
                             ' -- projected shadows')

    parser.add_argument('-l', '--loras', type=str, nargs="*", default=[],
                        help='Style-specific LoRA checkpoints to use.'
                             'It is recommended to experiment with style images first.'
                             'This feature can be used independently (with or without style images).'
                             'For LoRAs starting with ext_, the trigger words are not added automatically to prompt !!!'
                             'Currently supported are: ' + ', '.join(SUPPORTED_LORAS))
    parser.add_argument('-lw', '--loras_weights', type=float, nargs="*", default=[],
                        help='Weight of influence for each LoRA.'
                             'Should be exactly the same count as the loras parameter.'
                             'Recommended value is around 0.5')

    parser.add_argument('--direct_config_override', type=str, nargs='*', default=[],
                        help='Advanced feature. List of key=value pairs to override in the underlying generated config.'
                             'Changes are applied at the end, so can also override values implicated by other CLI params')
    # -------- END Copy from sd_experiments --------

    parser.set_defaults(command_func=schedule)


def schedule(
        backend_base: str,

        follow: bool,
        output: Optional[Path],

        input_meshes: str,
        style_images_paths: List[str],

        **kwargs,
):
    if len(style_images_paths) != len(kwargs['style_images_weights']):
        raise UsageError("style images and style images weights arguments should be in the same amount.")
    if len(kwargs['loras']) != len(kwargs['loras_weights']):
        raise UsageError("loras and loras_weights arguments should be in the same amount.")
    for lora in kwargs['loras']:
        if lora not in SUPPORTED_LORAS:
            raise UsageError(f'LoRA {lora} not in supported LoRA list: {list(SUPPORTED_LORAS)}')
    if kwargs['enable_4x_upscale'] and kwargs['disable_3d']:
        raise UsageError('Both enable_4x_upscale and disable_3d flags cannot be used together.')
    if len(kwargs['camera_yaws']) not in (1, kwargs['n_cameras']):
        raise UsageError('Camera yaws amount needs to be either 1 or --n_cameras')
    if len(kwargs['camera_pitches']) not in (1, kwargs['n_cameras']):
        raise UsageError('Camera pitches amount needs to be either 1 or --n_cameras')

    if output is not None:
        follow = True

    schedule_command = ServiceScheduleJobCommand(
        base_url=backend_base,
        data={**kwargs},
        files=[
            *[("style_images", open(sip, "rb")) for sip in style_images_paths],
            *[("input_meshes", open(imp, "rb")) for imp in input_meshes],
        ],
    )

    schedule_result = schedule_command.run()
    job_id = schedule_result["job_id"]
    print(f"Job ID: {job_id}")

    if follow:
        check_command = ServiceCheckStatusCommand(
            base_url=backend_base,
            job_id=job_id
        )

        while True:
            time.sleep(5)

            check_result = check_command.run()

            status = check_result["status"]
            progress = check_result["progress"]

            print(f"Job ID: {job_id}\nStatus: {status}\nProgress: {progress[0]}/{progress[1]}\n")

            if status == "FAILED":
                raise UsageError("Job failed")
            elif status == "SUCCEEDED":
                break

    if output:
        download_result(
            backend_base=backend_base,
            job_id=schedule_result["job_id"],
            output=output,
        )
