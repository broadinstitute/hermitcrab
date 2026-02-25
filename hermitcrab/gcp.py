import subprocess
import time
from typing import List, Union
import logging
import json
import requests
import re
from dataclasses import dataclass


class GCPPermissionError(Exception):
    pass


class AccessDenied(Exception):
    pass


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
    def __init__(self, msg):
        super().__init__(msg)
        self.error_message = msg


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
        raise GCPPermissionError(
            f'The current credentials gcloud is using doesn\'t have access to impersonate {service_account}. Grant "Service Account OpenID Connect Identity Token Creator" and "Service Account Token Creator" to this user to solve this.'
        )
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


def has_access_to_docker_image(service_account, docker_image):
    """Returns True if this service account has access to pull the docker image, otherwise
    False."""
    try:
        _check_access_to_docker_image(service_account, docker_image)
    except AccessDenied:
        return False
    return True


def _check_access_to_docker_image(service_account, docker_image):
    "Tests to make sure that the given service account can read the docker_image. Throws an assertion error if not"
    access_token = _get_access_token()

    service_account_access_token = _get_impersonating_access_token(
        access_token, service_account
    )

    parsed_image_name = parse_docker_image_name(docker_image)

    # Now attempt to retreive the docker image manifest to see if we have access. Expecting either success, manifest doesn't exist, or permission denied
    #    manifest_url = f"https://{parsed_image_name.host}:{parsed_image_name.port}/v2/{parsed_image_name.project}/{parsed_image_name.repository}/{parsed_image_name.image_name}/manifests/{parsed_image_name.tag}"
    manifest_url = f"https://{parsed_image_name.host}:{parsed_image_name.port}/v2/{parsed_image_name.path}/manifests/{parsed_image_name.tag}"
    # print("manifest_url", manifest_url)
    #    assert manifest_url == 'https://us-central1-docker.pkg.dev:443/v2/cds-docker-containers/docker/cds_python_jupyter/manifests/latest'

    #    manifest_url="https://us-central1-docker.pkg.dev:443/v2/us-central1-docker.pkg.dev/cds-docker-containers/docker/manifests/latest"
    res = requests.get(
        manifest_url,
        headers={"Authorization": f"Bearer {service_account_access_token}"},
    )

    #     with open("req.py", "wt") as fd:
    #         headers = {"Authorization": f"Bearer {service_account_access_token}"}
    #         fd.write(f"""
    # import requests

    # res = requests.get({repr(manifest_url)}, headers={headers})
    # print(res.status_code)
    # print(res.content)
    # """)

    reconstructed_image_name = str(parsed_image_name)

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


@dataclass
class DockerImageName:
    host: str
    port: int
    path: str
    tag: str


@dataclass
class ContainerRegistryPath(DockerImageName):
    region: str  # values like "" (if global), or a region like "asia", "eu", "us" etc
    project: str
    repository: str
    image_name: str


@dataclass
class ArtifactRegistryPath(DockerImageName):
    location: str  # values like "us", "us-central1", etc
    project: str
    repository: str
    image_name: str


def _default_to(value, default):
    if value is None or value == "":
        return default
    return value


def parse_docker_image_name(docker_image):
    m = re.match(
        r"(?:([a-z0-9-]+\\.[a-z0-9-.]+)?(?::(\\d+))?/)?([a-z0-9-_/]+)(?::([a-z0-9-_/.]+))?",
        docker_image,
    )
    if m is None:
        raise Exception(
            f'"{docker_image}" does not appear to be a valid docker image name'
        )
    host, port, path, tag = m.groups()

    # parse this as a generic name
    generic = DockerImageName(
        host=_default_to(host, "docker.io"),
        port=int(_default_to(port, "443")),
        path=path,
        tag=_default_to(tag, "latest"),
    )

    # Now check, is it a google container registry address like us.gcr.io/cds-docker-containers/gumbopot or gcr.io/cds-docker-containers/gumbopot
    m = re.match(r"^([a-z0-9-]+)\.gcr\.io$", generic.host)
    if m is not None:
        region = m.group(1)
        m = re.match(r"([a-z0-9-]+)/([a-z0-9-/_]+)", generic.path)
        assert (
            m
        ), f"Based on host, looks like GCR name, but the path was invalid: {generic.path}"
        project, image_name = m.groups()
        return ContainerRegistryPath(
            host=generic.host,
            port=generic.port,
            path=generic.path,
            tag=generic.tag,
            region=region,
            project=project,
            repository=generic.host,
            image_name=image_name,
        )

    # is it an artifact registry service like us-central1-docker.pkg.dev or us-docker.pkg.dev
    # example: us-central1-docker.pkg.dev/cds-docker-containers/docker/hermit-dev-env:v1
    m = re.match(r"^([a-z0-9-]+)-docker\.pkg\.dev$", generic.host)
    if m is not None:
        location = m.group(1)
        m = re.match(r"([a-z0-9-]+)/([a-z0-9-._]+)/([a-z0-9-/_]+)", generic.path)
        assert (
            m
        ), f"Based on host, looks like a Artifact Registry name, but path was invalid: {generic.path}"
        project, repository, image_name = m.groups()
        return ArtifactRegistryPath(
            host=generic.host,
            port=generic.port,
            path=generic.path,
            tag=generic.tag,
            location=location,
            project=project,
            repository=repository,
            image_name=image_name,
        )

    # if it's neither, just return the generic parsing
    return generic


def get_grant_instructions(service_account, docker_image):
    parsed_name = parse_docker_image_name(docker_image)

    if isinstance(parsed_name, ArtifactRegistryPath):
        return f"""Execute the following to grant access to hermit's service account:

gcloud artifacts repositories add-iam-policy-binding {parsed_name.repository} \\
    --location={parsed_name.location} \\
    --member='serviceAccount:{service_account}' \\
    --role='roles/artifactregistry.reader' \\
    --project='{parsed_name.project}'

After this has executed successfully, wait a few minutes (grants don't apply instantaneously)
and try your hermit operation again.
            """

    if isinstance(parsed_name, ContainerRegistryPath):
        return f"""The name {docker_image} suggests
that this image is hosted using google's Container Registry service, however that 
service is deprecated and it likely has been migrated over to Google's 
Arifact Registry service. 

To confirm this, go to https://console.cloud.google.com/artifacts?project={parsed_name.project} 
and confirm that you can see your image stored there.

Assuming you can find your image there, you can execute the following to grant access to hermit's service account:

gcloud artifacts repositories add-iam-policy-binding {parsed_name.host} \\
    --location={parsed_name.region if parsed_name.region != "" else "us"} \\
    --member='serviceAccount:{service_account}' \\
    --role='roles/artifactregistry.reader' \\
    --project='{parsed_name.project}'

After this has executed successfully, wait a few minutes (grants can take some time before they take effect)
and try your hermit operation again.
            """

    raise Exception(
        f"The name {docker_image} doesn't match the patterns for docker images hosted on google, and so no instructions can be provided."
    )
