import argparse

from pathlib import Path

from sd_cli.error import UsageError
from sd_cli.api.service import ServiceCheckStatusCommand
from sd_cli.utils.download_result import download_result


def add_subparser(subparsers):
    parser: argparse.ArgumentParser = subparsers.add_parser(
        name='download',
        help='Download output of already finished job',
        description='Download output of already finished job',
        formatter_class=argparse.MetavarTypeHelpFormatter,
    )


    parser.add_argument(
        '-j', '--job-id',
        action='store',
        type=str,
        required=True,
        help='Job ID whose result to download',
    )

    parser.add_argument(
        '-o', '--output',
        action='store',
        type=Path,
        required=True,
        help='Path where output will be downloaded. If ends with .zip, zip archive will be downloaded, '
             'otherwise folder with that name will be created, and output will be extracted into it.',
    )

    parser.set_defaults(command_func=download)


def download(
        backend_base: str,

        job_id: str,
        output: Path,

        **kwargs: dict,
):
    check_command = ServiceCheckStatusCommand(
        base_url=backend_base,
        job_id=job_id
    )

    check_result = check_command.run()

    status = check_result["status"]
    if status == "FAILED":
        raise UsageError("Cannot download output of failed job")
    elif status != "SUCCEEDED":
        raise UsageError("Job is still pending, wait until job is completed")

    download_result(backend_base, job_id, output)
