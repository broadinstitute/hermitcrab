import argparse
import sys
from .command import create, up, down


def main(argv=None):
    parse = argparse.ArgumentParser()
    subparser = parse.add_subparsers()

    create.add_command(subparser)
    up.add_command(subparser)
    down.add_command(subparser)

    args = parse.parse_args(argv)

    return args.func(args)


if __name__ == "__main__":
    main(sys.argv[1:])
