import hermitcrab


def add_command(subparser):
    def _version(args):
        print(hermitcrab.__version__)

    parser = subparser.add_parser(
        "version",
        help="Prints version information",
    )
    parser.set_defaults(func=_version)
