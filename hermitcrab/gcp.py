import subprocess
import time
from typing import List, Union
import logging
import json
import requests
import re
from .config import GRANT_MODE_ARTIFACT_REGISTRY, GRANT_MODE_INFER, GRANT_MODE_NONE

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


# a big of hack to work around the next for parents to reap threads. If children aren't reaped, then we can't check by pid
# if tunnel has shut down
_procs = []


def gcloud_in_background(args: List[Union[str, int]], log_path: str):
    cmd = _make_command(args)

    log_info(f"Running in the background: {cmd}")

    with open(log_path, "wt") as log_fd:
        proc = subprocess.Popen(
            cmd, stderr=subprocess.STDOUT, stdout=log_fd, stdin=subprocess.DEVNULL
        )

    log_info(f"Running as pid={proc.pid}")

    _procs.append(proc)

    return proc


def _check_procs():
    for proc in _procs:
        proc.poll()


def gcloud_capturing_output(
    args: List[str], ignore_error: bool = False, retries_on_timeout=0
):
    cmd = _make_command(args)
    attempt = 0
    while attempt <= retries_on_timeout:
        try:
            log_info(f"Executing, capturing output: {cmd}")

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
            )
            stdout, stderr = proc.communicate(timeout=10)
            stdout = stdout.decode("utf8")
            stderr = stderr.decode("utf8")
            log_debug(f"stdout: {stdout}")
            log_debug(f"stderr: {stderr}")
            if not ignore_error:
                assert (
                    proc.returncode == 0
                ), f"Executing {cmd} failed (return code: {proc.returncode}). Stderr: {stderr}"

            return stdout, stderr
        except subprocess.TimeoutExpired as ex:
            attempt += 1
            if attempt > retries_on_timeout:
                raise ex
            print(f"Attempt {attempt}: got {ex}. Retrying...")

    raise Exception("Code should not be reachable")


def gcloud_capturing_json_output(args: List[str]):
    cmd = _make_command(args)

    log_info(f"Executing, expecting json output: {cmd}")

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


class GCloudError(Exception):
    pass


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
    if proc.returncode != 0:
        raise GCloudError(
            f"Executing {cmd} failed (return code: {proc.returncode}). Output: {stdout}"
        )


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


class GCPPermissionError(Exception):
    pass


def _get_impersonating_access_token(access_token, service_account):
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
    if res.status_code == 403:
        raise GCPPermissionError()
    assert (
        res.status_code == 200
    ), f"Got an error trying to impersonate service account ({service_account}). status_code={res.status_code}, response content={res.content}"
    service_account_access_token = res.json()["accessToken"]
    return service_account_access_token


def _get_access_token():
    access_token = gcloud_capturing_json_output(
        ["auth", "print-access-token", "--format=json"]
    )["token"]
    return access_token


def wait_for_impersonating_access_token_success(
    service_account, retry_delay=5, max_wait=120
):
    print(
        "Waiting for grant to take effect... (May take awhile, but this only needs to happen once)"
    )
    access_token = _get_access_token()
    start = time.time()
    attempts = 0
    while True:
        attempts += 1
        try:
            _get_impersonating_access_token(access_token, service_account)
            break
        except GCPPermissionError:
            if (time.time() - start) > max_wait:
                raise Exception(
                    f"Failed to verify that permissions are set up for impersonification after {attempts} checks. Aborting"
                )

            time.sleep(retry_delay)


class AccessDenied(Exception):
    pass


def _check_access_to_docker_image(service_account, docker_image):
    "Tests to make sure that the given service account can read the docker_image. Throws an assertion error if not"
    access_token = _get_access_token()

    service_account_access_token = _get_impersonating_access_token(
        access_token, service_account
    )

    m = re.match("(^[^/]+)/([^:]+)(?::(.*))?", docker_image)
    assert m, f"Could not parse {docker_image} as an image name"
    docker_repo_host, image_name, reference = m.groups()
    if reference is None:
        reference = "latest"

    # Now attempt to retreive the docker image manifest to see if we have access. Expecting either success, manifest doesn't exist, or permission denied
    manifest_url = f"https://{docker_repo_host}/v2/{image_name}/manifests/{reference}"
    res = requests.get(
        manifest_url,
        headers={"Authorization": f"Bearer {service_account_access_token}"},
    )

    reconstructed_image_name = f"{docker_repo_host}/{image_name}:{reference}"

    if res.status_code == 200:
        # return if we were successful
        return

    if res.status_code == 404:
        raise Exception(
            f"Service account ({service_account}) has access to docker repo, but could not find image {reconstructed_image_name}"
        )

    if res.status_code in [403, 401]:
        raise AccessDenied(
            f"Service account ({service_account}) does not access to retreive image {reconstructed_image_name}"
        )

    raise AssertionError(
        f"Unexpected status_code={res.status_code} when fetching manifest from {manifest_url}, response body={res.content}"
    )


def _do_grant_access_to_artifact_registry(project, service_account, docker_image):
    grant_access_to_artifact_registry(project, service_account, False)
    wait_for_artifact_registry_access(service_account, docker_image)


def ensure_access_to_docker_image(service_account, docker_image, grant_mode):
    "If the docker image is hosted on artifact registry, will grant the required permissions to access the repo that contains the image"

    if grant_mode == GRANT_MODE_INFER:
        m = re.match("us.gcr.io/([^/]+)/(.+)", docker_image)

        if m is not None:
            raise Exception(
                "Docker image name suggests the image is hosted on google's (now deprecated) Container Registry service. These docker images are no longer supported. Its possible that this docker image may actually be hosted on Google's Artifact Registry service, and if so, set grant_mode in config file to \"artifact-registry:PROJECT_ID\" where PROJECT_ID is the owning google project ID"
            )
    elif grant_mode.startswith(GRANT_MODE_ARTIFACT_REGISTRY + ":"):
        _, project = grant_mode.split(":")
        _do_grant_access_to_artifact_registry(project, service_account, docker_image)

    elif grant_mode == GRANT_MODE_INFER:
        m = re.match("[^.]+.pkg.dev/([^/]+)/(.+)", docker_image)
        if m is not None:
            project = m.group(1)

            print(
                f"Based on the name, {docker_image} appears to be hosted on google's Artifact Registry. Granting access to {service_account} to make sure image can be pulled by VM"
            )
            _do_grant_access_to_artifact_registry(
                project, service_account, docker_image
            )
    else:
        assert grant_mode == GRANT_MODE_NONE
        _check_access_to_docker_image(service_account, docker_image)


def grant_access_to_artifact_registry(project, service_account, needs_write_access):
    if needs_write_access:
        role = "roles/artifactregistry.writer"
    else:
        role = "roles/artifactregistry.reader"

    print(f"Granting {role} on GCP project {project} to {service_account} ")
    gcloud(
        [
            "projects",
            "add-iam-policy-binding",
            project,
            f"--member=serviceAccount:{service_account}",
            f"--role={role}",
        ]
    )


def wait_for_artifact_registry_access(
    service_account, docker_image, retry_delay=5, max_wait=60 * 5
):
    start = time.time()
    attempt = 0
    while True:
        attempt += 1

        try:
            _check_access_to_docker_image(service_account, docker_image)
            break
        except AccessDenied as ex:
            if attempt == 1:
                print(
                    "Waiting for grant to take effect... (May take awhile, but this only needs to happen once)"
                )

            if (time.time() - start) > max_wait:
                raise Exception(
                    f"Failed to verify that permissions are set up for impersonification after {attempt} checks. Aborting"
                )

            time.sleep(retry_delay)
