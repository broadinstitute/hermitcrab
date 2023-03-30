import os
from config import CONTAINER_SSHD_PORT, get_config_dir, get_tunnel_status_dir
from gcp import gcloud_in_background


def is_tunnel_running(name: str):
    raise Exception("unimp")


def start_tunnel(name: str, zone: str, project: str, local_port: int):
    print(f"Starting tunnel on local port {local_port}...")
    tunnel_status_dir = get_tunnel_status_dir(create_if_missing=True)
    os.path.join(get_config_dir(), "tunnels")
    if not os.path.exists(tunnel_status_dir):
        os.makedirs(tunnel_status_dir)

    tunnel_log = os.path.join(tunnel_status_dir, f"{name}.log")
    tunnel_pid = os.path.join(tunnel_status_dir, f"{name}.log")
    pid = gcloud_in_background(
        [
            "compute",
            "start-iap-tunnel",
            name,
            CONTAINER_SSHD_PORT,
            f"--local-host-port=localhost:{local_port}",
            f"--zone={zone}",
            f"--project={project}",
        ],
        tunnel_log,
    )
    with open(tunnel_pid, "wt") as fd:
        fd.write(str(pid))


def stop_tunnel(name: str):
    raise Exception("unimp")
