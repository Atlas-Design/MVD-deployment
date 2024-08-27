import argparse

from prettytable import PrettyTable

from sd_cli.api.service import ServiceListJobsCommand


def add_subparser(subparsers):
    parser: argparse.ArgumentParser = subparsers.add_parser(
        name='list-jobs',
        help='List jobs',
        description='List jobs',
        formatter_class=argparse.MetavarTypeHelpFormatter,
    )

    parser.add_argument(
        '-a', '--all',
        action='store_true',
        required=False,
        default=False,
        help='List all jobs',
    )

    parser.set_defaults(command_func=list_jobs)


def list_jobs(
    backend_base: str,

    all: bool,

    **kwargs: dict,
):
    list_jobs_command = ServiceListJobsCommand(
        base_url=backend_base,
        all=all
    )

    check_result: list[dict] = list_jobs_command.run()
    table = PrettyTable()
    table.field_names = ["Job ID", "Created At", "Status", "Progress"]

    for job in check_result:
        table.add_row([job['job_id'], job['created_at'], job['status'], f"{job['progress'][0]}/{job['progress'][1]}"])

    print(table)
