from .. import gcp
from ..config import (
    get_min_instance_config,
    get_instance_names,
    config_exists,
    CONTAINER_SSHD_PORT,
    LONG_OPERATION_TIMEOUT,
)
from typing import Optional


def status(name: Optional[str]):
    if name:
        instance_config = get_min_instance_config(name)
        instance_configs = [instance_config]
    else:
        instance_configs = [
            get_min_instance_config(name) for name in get_instance_names()
        ]

    if config_exists("default"):
        default_instance_config = get_min_instance_config("default")
        default_instance_name = default_instance_config.name
    else:
        default_instance_name = None

    for instance_config in instance_configs:
        status = gcp.get_instance_status(
            instance_config.name,
            instance_config.zone,
            instance_config.project,
            one_or_none=True,
        )

        if status is None:
            status = "OFFLINE"

        default_label = ""
        if default_instance_name == instance_config.name:
            default_label = "(default)"

        print(f"{instance_config.name} {status} {default_label}")


def add_command(subparser):
    def _status(args):
        status(args.name)

    parser = subparser.add_parser(
        "status",
        help="Print status of all instances, or a single instance if specified",
    )
    parser.set_defaults(func=_status)
    parser.add_argument("name", help="The name of the instance to check", nargs="?")
