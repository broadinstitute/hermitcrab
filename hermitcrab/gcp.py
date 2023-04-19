import subprocess
import time
from typing import List, Union
import logging
import json
import requests
import re

log = logging.getLogger(__name__)


def log_info(msg):
    log.info("%s", msg)


def log_debug(msg):
    log.debug("%s", msg)


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

    with open(log_path, "wt") as log_fd:
        proc = subprocess.Popen(
            cmd, stderr=subprocess.STDOUT, stdout=log_fd, stdin=subprocess.DEVNULL
        )

    log_info(f"Running as pid={proc.pid}")

    return proc


def gcloud_capturing_json_output(args: List[str]):
    cmd = _make_command(args)

    log_debug(f"Executing, expecting json output: {cmd}")

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL
    )
    stdout, stderr = proc.communicate(timeout=10)
    stdout = stdout.decode("utf8")
    stderr = stderr.decode("utf8")
    log_debug(f"stdout: {stdout}")
    log_debug(f"stderr: {stderr}")
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
            print(f"VM {name} is now {status}")
        assert (
            time.time() - start_time < max_time
        ), f"Was waiting for status to change to {goal_status} but more than {max_time} seconds elapsed"
        prev_status = status
        time.sleep(5)


def sanity_check_docker_image(service_account, docker_image):
    "Tests to make sure that the given service account can read the docker_image. Throws an assertion error if not"

    # TODO: If this throws a permission error, try again after executing:
    #   gcloud iam service-accounts add-iam-policy-binding PRIV_SA \
    #     --member=serviceAccount:CALLER_SA --role=roles/iam.serviceAccountTokenCreator --format=json
    access_token = gcloud_capturing_json_output(
        ["auth", "print-access-token", "--format=json"]
    )["token"]

    # get an access token for impersonating service account so we can see if this account has rights to access the docker image
    res = requests.post(
        f"https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/{service_account}:generateAccessToken",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {access_token}",
        },
        data=json.dumps(
            {
                "scope": ["https://www.googleapis.com/auth/cloud-platform"],
                "lifetime": "300s",
            }
        ),
    )
    assert (
        res.status_code == 200
    ), f"Got an error trying to impersonate service account ({service_account}). status_code={res.status_code}, response content={res.content}"
    service_account_access_token = res.json()["accessToken"]

    m = re.match("(^[^/]+)/([^:]+)(?::(.*))?", docker_image)
    assert m, f"Could not parse {docker_image} as an image name"
    docker_repo_host, image_name, reference = m.groups()

    # Now attempt to retreive the docker image manifest to see if we have access. Expecting either success, manifest doesn't exist, or permission denied
    manifest_url = f"https://{docker_repo_host}/v2/{image_name}/manifests/{reference}"
    res = requests.get(
        manifest_url,
        headers={"Authorization": f"Bearer {service_account_access_token}"},
    )

    if res.status_code == 200:
        # return if we were successful
        return

    if res.status_code == 404:
        raise Exception(
            "Service account ({service_account}) has access to docker repo, but could not find image {docker_image}"
        )

    if res.status_code in [403, 401]:
        raise Exception(
            "Service account ({service_account}) does not access to retreive image {docker_image}"
        )

    raise AssertionError(
        f"Unexpected status_code={res.status_code} when fetching manifest from {manifest_url}, response body={res.content}"
    )


def get_default_service_account(project):
    service_accounts = gcloud_capturing_json_output(
        [
            "iam",
            "service-accounts",
            "list",
            f"--project={project}",
            "--filter=displayName='Compute Engine default service account'",
            "--format=json",
        ],
    )
    assert (
        len(service_accounts) == 1
    ), f"Could not determine default compute engine service account. (Find these possibilities: {service_accounts})"
    return service_accounts[0]["email"]
