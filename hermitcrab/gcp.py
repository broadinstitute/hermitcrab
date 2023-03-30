import subprocess
import time
from typing import List, Optional, Union
import logging
import json

log = logging.getLogger(__name__)


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

    log.info("%s", f"Running in the background: {cmd}")

    with open(log_path, "at") as log_fd:
        proc = subprocess.Popen(cmd, stderr=subprocess.STDOUT, stdout=log_fd)

    return proc.pid


def gcloud(args: List[str], capture_stdout: bool = False) -> Optional[str]:
    cmd = _make_command(args)

    log.info("%s", f"Executing: {cmd}")
    if capture_stdout:
        stdout = subprocess.check_output(cmd)
        return stdout.decode("utf8")
    else:
        subprocess.check_call(cmd)


def get_instance_status(name, zone, project, one_or_none=False):
    status_json = gcloud(
        [
            "compute",
            "instances",
            "list",
            f"--filter=name={name}",
            "--format=json",
            f"--zones={zone}",
            f"--project={project}",
        ],
        capture_stdout=True,
    )
    assert status_json is not None

    status = json.loads(status_json)

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
