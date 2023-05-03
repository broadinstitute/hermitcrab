from .. import gcp
from ..config import (
    get_min_instance_config,
    LONG_OPERATION_TIMEOUT,
    delete_instance_config,
)
from .down import is_tunnel_running


def delete(name: str, force: bool):
    instance_config = get_min_instance_config(name)

    assert not is_tunnel_running(
        instance_config.name
    ), "Tunnel appears to still be running. use 'hermit down ...' to shut down first"

    status = gcp.get_instance_status(
        instance_config.name,
        instance_config.zone,
        instance_config.project,
        one_or_none=True,
    )
    assert (
        status is None
    ), f"Instance is exists. Use 'hermit down ...' to remove instance before deleting configuration."

    if not force:
        print(
            f"Are you sure you want to delete the data volume associated with {instance_config.name}? This will irreversably delete the data on this disk!\n"
            f"If you are sure, type the name of the disk '{instance_config.pd_name}': ",
            end="",
        )
        disk_name = input()
        assert (
            disk_name == instance_config.pd_name
        ), f"typed value '{disk_name}' did not match the disk name '{instance_config.pd_name}'"

    print(f"Deleting persistent disk {instance_config.pd_name}")
    gcp.gcloud(
        [
            "compute",
            "disks",
            "delete",
            instance_config.pd_name,
            f"--zone={instance_config.zone}",
            f"--project={instance_config.project}",
        ],
        timeout=LONG_OPERATION_TIMEOUT,
    )

    print(f"Deleting config")
    delete_instance_config(instance_config.name)


def add_command(subparser):
    def _delete(args):
        delete(args.name, args.force)

    parser = subparser.add_parser(
        "delete",
        help="Delete the persistent disk associated with the specified instance config",
    )
    parser.set_defaults(func=_delete)
    parser.add_argument(
        "name",
        help="The name of the instance config to delete the volume for",
        nargs="?",
        default="default",
    )
    parser.add_argument(
        "-f",
        "--force",
        help="If specified, will not prompt user to confirm before deleting resources",
        action="store_true",
    )
