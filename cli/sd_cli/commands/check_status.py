import time
import argparse

from sd_cli.error import UsageError
from sd_cli.api.service import ServiceCheckStatusCommand


def add_subparser(subparsers):
    parser: argparse.ArgumentParser = subparsers.add_parser(
        name='check-status',
        help='Check status of a job',
        description='Check status of a job',
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
        '-f', '--follow',
        action='store_true',
        default=False,
        help='When set program will wait until job completes.',
    )

    parser.set_defaults(command_func=check_status)


def check_status(
        backend_base: str,

        job_id: str,
        follow: bool,

        **kwargs: dict,
):
    check_command = ServiceCheckStatusCommand(
        base_url=backend_base,
        job_id=job_id
    )

    while True:
        check_result = check_command.run()

        status = check_result["status"]
        progress = check_result["progress"]

        print(f"Job ID: {job_id}\nStatus: {status}\nProgress: {progress[0]}/{progress[1]}\n")

        if status == "FAILED":
            raise UsageError("Job failed")
        elif status == "SUCCEEDED":
            break

        if not follow:
            break

        time.sleep(5)
