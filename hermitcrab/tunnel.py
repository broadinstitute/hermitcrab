import os
from .config import CONTAINER_SSHD_PORT, get_tunnel_status_dir, LONG_OPERATION_TIMEOUT
from .gcp import gcloud_in_background, _check_procs
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


def is_port_listening(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(("localhost", port))
    except ConnectionRefusedError:
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


def delete_pid(name: str):
    tunnel_status_dir = get_tunnel_status_dir(create_if_missing=True)
    tunnel_pid_file = os.path.join(tunnel_status_dir, f"{name}.pid")

    if os.path.exists(tunnel_pid_file):
        os.unlink(tunnel_pid_file)


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

    def attempt_start():
        proc = gcloud_in_background(
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

        wait_for_proc_to_die_or_port_listening(
            proc, local_port, LONG_OPERATION_TIMEOUT, tunnel_log
        )

        with open(tunnel_pid, "wt") as fd:
            fd.write(str(proc.pid))

    retry_on_exception(attempt_start, UnexpectedTermination)
    print(f"Tunnel on port {local_port} started.")
    print("You should now be able to execute the following to connect to the instance:")
    print("")
    print(f"  ssh {name}")
    print("")


verbose = False


def retry_on_exception(callback, expected_exception, retry_delay=10, max_attempts=10):
    count = 0
    while True:
        count += 1

        try:
            callback()
            break
        except expected_exception as ex:
            if verbose:
                print(f"Caught {ex}, retrying {count} out of {max_attempts}...")

            if count >= max_attempts:
                raise ex

        time.sleep(retry_delay)


class UnexpectedTermination(Exception):
    pass


def wait_for_proc_to_die_or_port_listening(proc, local_port, timeout, log_path):
    start = time.time()
    while True:
        if proc.poll() is not None:
            # if it has stopped, we have a problem
            if verbose:
                with open(log_path, "rt") as fd:
                    log = fd.read()
                print(log)
            raise UnexpectedTermination("start-iap-tunnel terminated unexpectedly")

        if is_port_listening(local_port):
            break

        assert time.time() - start < timeout
        time.sleep(1)


MAX_PROCESS_TERM_TIME = 10
# how many seconds to wait after TERM signal is sent before reporting an error
import time


def stop_tunnel(name: str):
    pid = read_pid(name)
    if pid is None:
        return
    print(f"Stopping tunnel (by terminating pid={pid})")
    os.kill(pid, signal.SIGTERM)

    start_time = time.time()
    while True:
        _check_procs()

        if not is_pid_valid(pid):
            break
        elapsed = time.time() - start_time
        assert (
            elapsed < MAX_PROCESS_TERM_TIME
        ), f"Giving up waiting for tunnel process (pid: {pid}) to terminate after {elapsed} seconds"
