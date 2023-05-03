from ..config import get_instance_configs, get_instance_config
from ..ssh import update_ssh_config


def update_ssh():
    update_ssh_config(get_instance_configs())


def add_command(subparser):
    def _update_ssh(args):
        update_ssh()

    parser = subparser.add_parser(
        "update_ssh",
        help="Rewrites the information in ~/.ssh/config with information for each of the instance configs. (This should automatically happen as a result of the 'hermit create ...' command, but this is a way to run this manually)",
    )
    parser.set_defaults(func=_update_ssh)
