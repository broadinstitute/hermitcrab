import os
from .config import CONTAINER_SSHD_PORT, get_tunnel_status_dir
from .gcp import gcloud_in_background
import socket
import signal


def is_pid_valid(pid):
    "returns True if there exists a process with the given PID"
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True


def is_port_free(port):
    "return true if we expect we can listen to the given TCP port on localhost"
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("localhost", port))
    except socket.error:
        return False
    finally:
        s.close()
    return True


def read_pid(name: str):
    tunnel_status_dir = get_tunnel_status_dir(create_if_missing=True)
    tunnel_pid_file = os.path.join(tunnel_status_dir, f"{name}.pid")

    if os.path.exists(tunnel_pid_file):
        with open(tunnel_pid_file, "rt") as fd:
            return int(fd.read())
    return None


def is_tunnel_running(name: str):
    pid = read_pid(name)
    return pid is not None and is_pid_valid(pid)


def start_tunnel(name: str, zone: str, project: str, local_port: int):
    assert is_port_free(
        local_port
    ), f"Cannot start tunnel because port {local_port} is already in use. (execute 'lsof -i tcp:{local_port}' to see which process is using it')"
    print(f"Starting tunnel on local port {local_port}...")

    tunnel_status_dir = get_tunnel_status_dir(create_if_missing=True)

    tunnel_log = os.path.join(tunnel_status_dir, f"{name}.log")
    tunnel_pid = os.path.join(tunnel_status_dir, f"{name}.pid")
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
    pid = read_pid(name)
    if pid is None:
        return
    print(f"Stopping tunnel (by terminating pid={pid})")
    os.kill(pid, signal.SIGTERM)
