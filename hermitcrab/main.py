import argparse
import sys
from .command import create, up, down, update_ssh
import logging


def main(argv=None):
    logging.basicConfig(filename="hermit.log", filemode="a", level=logging.INFO)

    parse = argparse.ArgumentParser()
    subparser = parse.add_subparsers()

    create.add_command(subparser)
    up.add_command(subparser)
    down.add_command(subparser)
    update_ssh.add_command(subparser)

    args = parse.parse_args(argv)

    return args.func(args)


if __name__ == "__main__":
    main(sys.argv[1:])
