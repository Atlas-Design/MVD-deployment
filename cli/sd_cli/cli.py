from .commands import root, download, check_status, schedule, cancel
from .error import UsageError


def cli():
    root_parser, command_subparsers = root.create_parser()

    download.add_subparser(command_subparsers)
    check_status.add_subparser(command_subparsers)
    schedule.add_subparser(command_subparsers)
    cancel.add_subparser(command_subparsers)

    args = root_parser.parse_args()

    try:
        args.command_func(**args.__dict__)
    except UsageError as e:
        root_parser.exit(2, f'error: {e}')
