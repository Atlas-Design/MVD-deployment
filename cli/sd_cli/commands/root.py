import argparse

from sd_cli.version import __version__


def create_parser():
    root_parser = argparse.ArgumentParser()
    root_parser.add_argument(
        '--version', action='version',
        version='%(prog)s, version {version}'.format(version=__version__)
    )

    root_parser.add_argument("--backend_base", type=str, default="http://34.140.119.26:3000", help="Backend base URL")

    command_subparsers = root_parser.add_subparsers(dest='command', metavar='COMMAND', required=True)

    return root_parser, command_subparsers
