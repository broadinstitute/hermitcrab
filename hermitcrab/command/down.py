from ..gcp import gcloud
from ..tunnel import is_tunnel_running, stop_tunnel
from ..config import get_instance_config


def down(name: str):
    instance_config = get_instance_config(name)
    assert instance_config is not None, f"Could not file config for {name}"

    if is_tunnel_running(instance_config.name):
        stop_tunnel(instance_config.name)

    print(f"Deleting instance {instance_config.name}")
    gcloud(
        [
            "compute",
            "instances",
            "delete",
            instance_config.name,
            f"--zone={instance_config.zone}",
            f"--project={instance_config.project}",
        ]
    )
