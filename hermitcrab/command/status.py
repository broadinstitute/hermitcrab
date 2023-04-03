from ..gcp import gcloud, get_instance_status
from ..config import get_instance_config, CONTAINER_SSHD_PORT, LONG_OPERATION_TIMEOUT


def status(name):
    instance_config = get_instance_config(name)
    assert instance_config is not None, f"Could not file config for {name}"

    status = get_instance_status(
        instance_config.name,
        instance_config.zone,
        instance_config.project,
        one_or_none=True,
    )

    if status is None:
        status = "OFFLINE"

    print(status)


def add_command(subparser):
    def _status(args):
        status(args.name)

    parser = subparser.add_parser("status", help="Print status of this instance")
    parser.set_defaults(func=_status)
    parser.add_argument(
        "name",
        help="The name of the instance to check",
        nargs="?",
        default="default",
    )
