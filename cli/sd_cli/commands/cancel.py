import time
import argparse

from sd_cli.error import UsageError
from sd_cli.api.service import ServiceCheckStatusCommand, ServiceCancelJobCommand


def add_subparser(subparsers):
    parser: argparse.ArgumentParser = subparsers.add_parser(
        name='cancel',
        help='Cancel job',
        description='Cancel job',
        formatter_class=argparse.MetavarTypeHelpFormatter,
    )

    parser.add_argument(
        '-j', '--job-id',
        action='store',
        type=str,
        required=True,
        help='Job ID whose result to download',
    )

    parser.set_defaults(command_func=check_status)


def check_status(
        backend_base: str,

        job_id: str,

        **kwargs: dict,
):
    check_command = ServiceCancelJobCommand(
        base_url=backend_base,
        job_id=job_id
    )

    check_result = check_command.run()

    status = check_result["status"]
    progress = check_result["progress"]

    print(f"Job ID: {job_id}\nStatus: {status}\nProgress: {progress[0]}/{progress[1]}\n")
