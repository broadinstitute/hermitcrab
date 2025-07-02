from .. import gcp
from ..tunnel import is_tunnel_running, stop_tunnel
from ..config import get_instance_config, LONG_OPERATION_TIMEOUT
import time
import subprocess


def wait_for_instance_termination(instance_config, timeout):
    deadline = time.time() + timeout
    last_status = None
    while True:
        status = gcp.get_instance_status(
            instance_config.name,
            instance_config.zone,
            instance_config.project,
            one_or_none=True,
        )

        if status != last_status:
            print(f"Instance {instance_config.name} is now {status}...")
            last_status = status

        if status == "TERMINATED":
            break

        if time.time() > deadline:
            raise TimeoutError()

        time.sleep(2)


def down(name: str):
    instance_config = get_instance_config(name)

    if is_tunnel_running(instance_config.name):
        stop_tunnel(instance_config.name)
    else:
        print("Tunnel appears to already be stopped")

    status = gcp.get_instance_status(
        instance_config.name,
        instance_config.zone,
        instance_config.project,
        one_or_none=True,
    )
    if status is None:
        print(f"Instance appears to be offline already.")
    else:
        if status == "RUNNING":
            print(f"Requesting graceful shutdown of {instance_config.name}...")

            try:
                gcp.gcloud(
                    [
                        "compute",
                        "ssh",
                        instance_config.name,
                        "--tunnel-through-iap",
                        f"--zone={instance_config.zone}",
                        f"--project={instance_config.project}",
                        "--command",
                        "sudo shutdown now",
                    ],
                    timeout=20,
                )
            except subprocess.TimeoutExpired:
                print("Timeout expired waiting for command to terminate")

            # allow 5 minutes for graceful shutdown
            print("Waiting 5 minutes for graceful shutdown to complete")
            try:
                wait_for_instance_termination(instance_config, timeout=5 * 60)
            except TimeoutError:
                pass

        print(f"Requesting deletion of {instance_config.name}...")
        gcp.gcloud(
            [
                "compute",
                "instances",
                "delete",
                instance_config.name,
                f"--zone={instance_config.zone}",
                f"--project={instance_config.project}",
            ],
            timeout=LONG_OPERATION_TIMEOUT,
        )


def add_command(subparser):
    def _down(args):
        down(args.name)

    parser = subparser.add_parser(
        "down",
        help="Delete instance (file system on associated disk will remain and an equivilent server can be brought up with the 'up' command)",
    )
    parser.set_defaults(func=_down)
    parser.add_argument(
        "name",
        help="The name to use when creating instance",
        nargs="?",
        default="default",
    )
