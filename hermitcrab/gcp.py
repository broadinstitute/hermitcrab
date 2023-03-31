import subprocess
import time
from typing import List, Optional, Union
import logging
import json

log = logging.getLogger(__name__)


def log_info(msg):
    log.info("%s", msg)


def _make_command(args):
    for x in args:
        assert (
            isinstance(x, str) or isinstance(x, int) or isinstance(x, float)
        ), f"{x} not an expected type"
    args = [str(x) for x in args]

    cmd = ["gcloud"] + args

    return cmd


def gcloud_in_background(args: List[Union[str, int]], log_path: str):
    cmd = _make_command(args)

    log_info(f"Running in the background: {cmd}")

    with open(log_path, "at") as log_fd:
        proc = subprocess.Popen(
            cmd, stderr=subprocess.STDOUT, stdout=log_fd, stdin=subprocess.DEVNULL
        )

    log_info(f"Running as pid={proc.pid}")

    return proc.pid


def gcloud_capturing_json_output(args: List[str]):
    cmd = _make_command(args)

    log_info(f"Executing, expecting json output: {cmd}")

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL
    )
    stdout, stderr = proc.communicate(timeout=10)
    stdout = stdout.decode("utf8")
    stderr = stderr.decode("utf8")
    log_info(f"stdout: {stdout}")
    log_info(f"stderr: {stderr}")
    assert (
        proc.returncode == 0
    ), f"Executing {cmd} failed (return code: {proc.returncode}). Output: {stderr}"

    return json.loads(stdout)


def gcloud(args: List[str], timeout=10):
    cmd = _make_command(args)

    log_info(f"Executing: {cmd}")
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL
    )
    stdout, stderr = proc.communicate(timeout=timeout)
    assert stderr is None
    stdout = stdout.decode("utf8")
    log_info(f"output: {stdout}")
    assert (
        proc.returncode == 0
    ), f"Executing {cmd} failed (return code: {proc.returncode}). Output: {stdout}"


def get_instance_status(name, zone, project, one_or_none=False):
    status = gcloud_capturing_json_output(
        [
            "compute",
            "instances",
            "list",
            f"--filter=name={name}",
            "--format=json",
            f"--zones={zone}",
            f"--project={project}",
        ],
    )
    if one_or_none:
        if len(status) == 0:
            return None
    assert len(status) == 1

    return status[0]["status"]


def wait_for_instance_status(name, zone, project, goal_status, max_time=5 * 60):
    prev_status = None
    start_time = time.time()
    while True:
        status = get_instance_status(name, zone, project)
        if status == goal_status:
            break
        if status != prev_status:
            print(f"status became {status}")
        assert (
            time.time() - start_time < max_time
        ), f"Was waiting for status to change to {goal_status} but more than {max_time} seconds elapsed"
        prev_status = status
        time.sleep(5)
