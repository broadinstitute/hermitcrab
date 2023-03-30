from ..config import get_instance_configs
from ..ssh import update_ssh_config


def update_ssh():
    update_ssh_config(list(get_instance_configs().values()))


def add_command(subparser):
    def _update_ssh(args):
        update_ssh()

    parser = subparser.add_parser(
        "update_ssh",
    )
    parser.set_defaults(func=_update_ssh)
