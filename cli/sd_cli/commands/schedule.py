from typing import List, Optional

import math
import time
import argparse

from pathlib import Path

from sd_cli.error import UsageError
from sd_cli.utils.download_result import download_result
from sd_cli.api.service import ServiceScheduleJobCommand, ServiceCheckStatusCommand

SUPPORTED_LORAS = {
    'japanese_shop_v0.1',
    'cyberpunk_v0.1',
    'prahov_v0.1',

    'ext_ghiblism',
    'ext_cyberpunk',
    'ext_buildingface',
    'ext_cyberpunk_fantasy',
    'ext_isometric',
    'ext_desert',

    'ext_add_detail',
}

SUPPORTED_SD_VERSIONS = ['sd1.5', 'sdxl', 'flux1dev']

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

    parser.add_argument('--workdir', type=Path, default="/workdir/generated_workdir/",
                        help='A path where all the input data will be rewritten, and results saved. '
                             'Needs to start with /workdir/ which is mounted `pwd` outside the docker environment. '
                             'Note that this is the only path in the CLI that is in-container. '
                             'Leaving default value is recommended.')

    parser.add_argument('--pos_prompt', type=str,
                        default="best quality, a multi-floor building, extremely detailed, a lot of windows",
                        help='A positive SD prompt to use. For flux can be split with || into clip_l||t5xxl')
    parser.add_argument('--neg_prompt', type=str, default="worst quality, bad quality, simple",
                        help='A negative SD prompt to use. For flux can be split with || into clip_l||t5xxl')
    parser.add_argument('--prompt_strength', type=float, default=7.5,
                        help="Classifier-free guidance scale. It's basically the text prompting weight.")
    parser.add_argument('--random_seed', type=int, default=42,
                        help="Global random seed for the whole pipeline")
    parser.add_argument('--sd_version', type=str, default='sd1.5', choices=SUPPORTED_SD_VERSIONS,
                        help=f'Which version of sd to use, one of {SUPPORTED_SD_VERSIONS}.')
    parser.add_argument('--uv_texture_resolution', type=int, nargs=2, default=(2560, 2560),
                        metavar=('RGB_UV_TEXTURE_RESOLUTION', 'DISPLACEMENT_UV_TEXTURE_RESOLUTION'),
                        help="Baked UV RGB and displacement textures resolutions (2 integers) for the final mesh."
                             "But when you use with --enable_uv_texture_upscale, the resolution will be determined"
                             "by the uv upscaling settings (--uv_upscale_resolution)."
                             "Lower values is slightly lower processing time. "
                             "Only relevant if disable_3d flag is not set."
                             "When running with lower upscaling (e.g. disabled upscaling flags), "
                             "it is safe to keep at lower value without much detail loss -- e.g. 1280."
                             "High values especially slows down pipeline.")
    parser.add_argument('--stages_upscale', type=float, nargs=3, default=(1, 1.9, -1),
                        metavar=tuple([f'STAGE_{i}_UPSCALE' for i in range(1, 4)]),
                        help="Multiplier for the generated image size per-stage."
                             "For stage 1 it means the starting resolution multiplier."
                             "By default (upscale 1.0) a stage 1 diffusion image resolution is roughly 512^2 pixels per one camera --"
                             "it is not exact value as it is rounded to block size of 8 and aspect ratio adjustment."
                             "The final multi-view diffusion generated image resolution will be roughly:"
                             " `n_cameras * 512^2 * stages_upscale[0] * stages_upscale[1] * stages_upscale[2]`. "
                             "Values are relevant only when relevant stages_enable flag are set. "
                             "The higher the values the slower the processing time. "
                             "Keep in mind the uv_texture_resolution value -- "
                             "too small uv_texture_resolution parameter value will not utilize "
                             "high upscaling factors values properly. "
                             "Therefore, high-res information can be lost "
                             "when projecting RGB data to UV space in such case. ")
    parser.add_argument('--stages_steps', type=int, nargs=3, default=(24, 24, -1),
                        metavar=tuple([f'STAGE_{i}_STEPS' for i in range(1, 4)]),
                        help="Amount of diffusion steps for generating non-upscaled multi-view image."
                             "Lower values will usually cause blurry/noisy/distorted/undetailed image."
                             "Has relatively marginal effect on processing speed unless almost everything else "
                             "possible is disabled for performance."
                             "There should be always 3 values -- for each of 3 diffusion stages."
                             "Second and third value relevant only when stage 2 and/or 3 enabled.")
    parser.add_argument('--stages_denoise', type=float, nargs=3, default=(1.0, 0.45, 0.2),
                        metavar=tuple([f'STAGE_{i}_DENOISE' for i in range(1, 4)]),
                        help="How much image can be changed on upscaling stages."
                             "Setting too high may cause too much "
                             " repeatable and distorted geometry to be generated. "
                             "Only relevant when relevant stages_enable flags are set. "
                             "Stage 1 denoise can be < 1 only with enable_rgb_prior flag set. ")

    parser.add_argument('--depth_algorithm', type=str, default='DepthAnythingV2',
                        help='Depth estimation is a necessary stage for displacement generation. '
                             'Supported values are "Marigold" or "DepthAnythingV2". ')
    parser.add_argument('--displacement_quality', type=int, default=2,
                        help="Only relevant if depth_algorithm argument value is Marigold."
                             "Higher values will produce a little bit less noisy displacement,"
                             "but slow down the pipeline significantly."
                             "Only relevant when disable_displacement flag is not set."
                             "Setting beyond ~12 is not recommended as the results will likely be no better afterwards "
                             " and processing much slower")
    parser.add_argument('--displacement_strength', type=float, default=0.05,
                        help="Simply displacement strength on the final mesh "
                             "(which is normalized so that avg. bounding box dimension size is 1)")
    parser.add_argument('--displacement_rgb_derivation_weight', type=float, default=0,
                        help='Only relevant if disable_displacement flag is not set.'
                             'A value from range <0, 1> interpolating between estimated displacement'
                             'and simple adjusted grayscaled RGB image. When > 0, generated displacement will affected '
                             'by color brightness, displacing e.g. shadows or normally flat patterns.'
                             'When ==1, it speeds up pipeline because it then disables depth estimation completely.'
                             'When == 0, it will be 100 percent based on depth estimation.')

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

    parser.add_argument('--total_remesh_mode', type=str, default='none',
                        help='One of "none", "smooth_generic", "sharp_generic", "smooth_organic", '
                             '"none_organic", "hard_surface", "smoothed_hard_surface".'
                             'It runs complex input mesh preprocessing if !="none".'
                             'See CLI examples for understanding how options work'
                             ' -- functionality hard to describe in text.')
    parser.add_argument('--apply_displacement_to_mesh', action='store_true', default=False,
                        help="WARNING: enabling this flat makes the final result very large "
                             "-- roughly 200-300MB high-poly mesh."
                             "Relevant only when disable_3d and disable_displacement flags are not set. "
                             "Create a very high-poly mesh with applied displacement as a blender modifier, "
                             "and material with bump mapping using the same displacement map.")

    parser.add_argument('--disable_3d', action='store_true', default=False,
                        help="Skip everything related to 3D, generate just the multi-view image "
                             "and it's depth if it is not disabled")
    parser.add_argument('--stages_enable', type=int, nargs=3, default=(1, 1, 0),
                        help="Sets whether the diffusion stages are enabled/disabled."
                             "Stage 1 can be disabled only with --enable_rgb_prior flag.")
    parser.add_argument('--disable_displacement', action='store_true', default=False,
                        help="Don't generate displacement maps. Faster processing time."
                             "In case of running disable_3d, it skips generating depth maps.")
    parser.add_argument('--enable_uv_texture_upscale', type=int, nargs=2, default=(0, 0),
                        metavar=('ENABLE_RGB_UV_TEXTURE_UPSCALE', 'ENABLE_DISPLACEMENT_UV_TEXTURE_UPSCALE'),
                        help="Upscale RGB and/or displacement (if applies) UV textures 4x. "
                             "Relevant only when disable_3d flag is not set. "
                             "Significantly slows down pipeline.")
    parser.add_argument('--uv_upscale_resolution', type=int, nargs=4, default=(2560, 8192, 2560, 8192),
                        metavar=('RGB_LOW', 'RGB_HIGH', 'DISPLACEMENT_LOW', 'DISPLACEMENT_HIGH'),
                        help="Only relevant if equivalent (for rgb or displacement) enable_uv_texture_upscale flag is set. "
                             "Final UV texture resolution will be the upper value."
                             "UV textures in the final texture processing stage are: \n"
                             "a) rescaled from processing resolution to the lower resolution\n "
                             "b) upscaled 4x\n "
                             "c) rescaled to the upper resolution")
    parser.add_argument('--enable_semantics', action='store_true', default=False,
                        help="Enable semantic segmentation output for buildings."
                             "Significantly slows down pipeline.")
    parser.add_argument('--enable_rgb_prior', action='store_true', default=False,
                        help="Enable rendering of rgb prior. Requires input mesh that contains already some RGB UV texture.")
    parser.add_argument('--enable_mesh_segmentation', action='store_true', default=False,
                        help="EXPERIMENTAL: Enable decomposing input mesh into segment for processing them separately "
                             "and combining them at the end.")

    parser.add_argument('-i', '--input_meshes', type=file_type, nargs="+", required=True,
                        help='List of paths to input massing .obj, .fbx or .glb files.')
    parser.add_argument('-s', '--style_images_paths', type=file_type, nargs="*", default=[],
                        help='Paths to input style images that will influence the result')
    parser.add_argument('-sw', '--style_images_weights', type=float, nargs="*", default=[],
                        help='Weight of influence for each style image.'
                             'It is possible to pass the amount equal to the amount of given style_images_paths,'
                             'or 3x more -- in the second case the weights will be specified for each pipeline stage.'
                             'For example of 2 style images A and B it is: '
                             'stage1_A stage1_B stage2_A stage2_B stage3_A stage3_B.'
                             'Recommended value is around 0.3.')
    parser.add_argument('--style_images_weight_types', type=str, nargs="*", default=[],
                        help='Weight type for each style image. '
                             'Specify like style weights.')
    parser.add_argument('--style_images_combine_embeds', type=str, nargs="*", default=[],
                        help='Combine embeds parameter per image. '
                             'Specify like style weights.')
    parser.add_argument('--style_images_start_ats', type=float, nargs="*", default=[],
                        help='When to start applying IP adapter. Allowed value range: 0.0-1.0). '
                             'Specify like style weights.')
    parser.add_argument('--style_images_end_ats', type=float, nargs="*", default=[],
                        help='When to stop applying IP adapter. Allowed value range: 0.0-1.0). '
                             'Specify like style weights.')

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

    CN_METAVAR = ("STRENGTH", "START_PERCENT", "END_PERCENT")
    parser.add_argument('--stage_1_cn_depth', type=float, nargs=3, default=(0.5, 0, 0.5), metavar=CN_METAVAR,
                        help='Stage 1 diffusion depth ControlNet settings, 3 values: '
                             ' strength, start_percentage, end_percentage. '
                             'It controls how much the generation follows the original shape '
                             '(represented as depth map rendered from all camera views). '
                             'Strength ==0 means that it should be disabled, maximum allowed strength is 1.0.'
                             'Start and end percentages control at which steps during diffusion it is applied: '
                             'Early end percentage means that diffusion will generate details at will without following the depth prior. '
                             'It means that lower end percentage can be often effectively similar to lowering strength. '
                             'Tweaking start percentage (setting >0) is usually not recommended as the image generation process will start unguided, '
                             'and later it will try to fit the desired object shape. ')
    parser.add_argument('--stage_1_cn_normal', type=float, nargs=3, default=(0.5, 0, 0.5), metavar=CN_METAVAR,
                        help='Similar to --stage_1_cn_depth but for stage 1 normalmap ControlNet. '
                             'Normalmap control helps more with preserving the original geometry details, '
                             'which means that it is not desired to be to have too much strength when trying to generate some new details. ')
    parser.add_argument('--stage_1_cn_canny', type=float, nargs=3, default=(0, -1, -1), metavar=CN_METAVAR,
                        help='Similar to --stage_1_cn_depth but for stage 1 canny ControlNet. '
                             'Canny control helps more with preserving the original texture patterns (not color). '
                             'Only relevant when enable_rgb_prior flag is set. ')

    parser.add_argument('--stage_2_cn_scribble', type=float, nargs=3, default=(0.5, 0, 0.5), metavar=CN_METAVAR,
                        help='Similar to --stage_1_cn_depth but for stage 2 scribble ControlNet. '
                             'Strong control here, enables preserving patterns generated in stage 1.')
    parser.add_argument('--stage_2_cn_depth', type=float, nargs=3, default=(0.5, 0, 0.5), metavar=CN_METAVAR,
                        help='Similar to --stage_1_cn_depth but for stage 2 depth ControlNet. ')
    parser.add_argument('--stage_2_cn_normal', type=float, nargs=3, default=(0.5, 0, 0.5), metavar=CN_METAVAR,
                        help='Similar to --stage_1_cn_depth but for stage 2 normalmap ControlNet. ')

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
    print(kwargs['pos_prompt'])

    if len(kwargs['style_images_weights']) not in (len(style_images_paths), len(style_images_paths) * 3):
        raise UsageError('style images and style images weights arguments should be in the same amount or 3x.')
    if len(kwargs['loras']) != len(kwargs['loras_weights']):
        raise UsageError("loras and loras_weights arguments should be in the same amount.")
    for lora in kwargs['loras']:
        if lora not in SUPPORTED_LORAS:
            raise UsageError(f'LoRA {lora} not in supported LoRA list: {list(SUPPORTED_LORAS)}')
    if any(kwargs['enable_uv_texture_upscale']) and kwargs['disable_3d']:
        raise UsageError('Both enable_uv_texture_upscale and disable_3d flags cannot be used together.')
    if len(kwargs['camera_yaws']) not in (1, kwargs['n_cameras']):
        raise UsageError('Camera yaws amount needs to be either 1 or --n_cameras')
    if len(kwargs['camera_pitches']) not in (1, kwargs['n_cameras']):
        raise UsageError('Camera pitches amount needs to be either 1 or --n_cameras')

    total_remesh_mode_options = {'none', 'smooth_generic', 'sharp_generic', 'smooth_organic', 'none_organic',
                                 'hard_surface', 'smoothed_hard_surface'}
    if kwargs['total_remesh_mode'] not in total_remesh_mode_options:
        raise UsageError(f'{kwargs["total_remesh_mode"]=} not in {total_remesh_mode_options}')
    depth_options = {'Marigold', 'DepthAnythingV2'}
    if kwargs['depth_algorithm'] not in depth_options:
        raise ValueError(f'{kwargs["depth_algorithm"]=} not in {depth_options}')

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
            logs = check_result["logs"]

            print(f"Job ID: {job_id}\nStatus: {status}\nProgress: {progress[0]}/{progress[1]}\n")

            if status in {"FAILED", "CANCELLED"}:
                if logs is not None:
                    print(f"Logs from failed stage: ")
                    print(logs)

                raise UsageError("Job failed")
            elif status == "SUCCEEDED":
                break

    if output:
        download_result(
            backend_base=backend_base,
            job_id=schedule_result["job_id"],
            output=output,
        )
