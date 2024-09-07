import argparse
import sys
from .command import create, up, down, update_ssh, status, delete, version
import logging


def main(argv=None):
    logging.basicConfig(filename="hermit.log", filemode="a", level=logging.INFO)

    parse = argparse.ArgumentParser()
    subparser = parse.add_subparsers()

    create.add_command(subparser)
    up.add_command(subparser)
    down.add_command(subparser)
    update_ssh.add_command(subparser)
    status.add_command(subparser)
    delete.add_command(subparser)
    version.add_command(subparser)

    def print_help(args):
        parse.print_help()

    parse.set_defaults(func=print_help)
    args = parse.parse_args(argv)

    return args.func(args)


if __name__ == "__main__":
    main(sys.argv[1:])
