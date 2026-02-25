from .. import gcp
import string, random
from ..config import (
    write_default_service_account,
    read_default_service_account,
    NoDefaultServiceAccount,
)
import os
from .. import __version__
import time

roles_to_add = [
    "roles/editor",  # Eventually figure out the minimal permissions
]


def random_string(length):
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


def get_or_create_default_service_account(project):
    # try reading it, and if it does not exist, create one
    try:
        return read_default_service_account(project)
    except NoDefaultServiceAccount:
        print(
            "Appears this may be the first time you've used hermit -- creating service account and enabling APIs"
        )
        enable_apis(project)
        create_service_account(project, None)

    return read_default_service_account(project)


def _retry_on_gcloud_error(
    action, attempts=10, sleep_duration=10, expected_error_message="", not_an_error=None
):
    last_error = None
    for i in range(attempts):
        try:
            action()
            return
        except gcp.GCloudError as e:
            last_error = e
            if not_an_error is not None and not_an_error in e.error_message:
                return
            if expected_error_message in e.error_message:
                print(
                    f"Got an error which is likely transient. Retrying in {sleep_duration} seconds..."
                )
        time.sleep(sleep_duration)

    print(f"Too many failed attempts -- raising error")
    assert last_error is not None
    raise last_error


def enable_apis(project):
    # if the service is already enabled, then this is a no-op
    gcp.gcloud(
        ["services", "enable", "compute.googleapis.com", "--project", project],
        timeout=60 * 10,
    )
    # This seems to be specific to the Broad: After enabling the compute API, there's no default network
    # so create one now since we need it to create the VM
    _retry_on_gcloud_error(
        lambda: gcp.gcloud(
            ["compute", "networks", "create", "default", "--project", project],
            timeout=60,
        ),
        expected_error_message="Compute Engine API has not been used in project",
        not_an_error="already exists",
    )


def _perform_grants(service_account_name, project):
    for i in range(10):
        try:
            for role in roles_to_add:
                grant(service_account_name, project, role)
                return
        except gcp.GCloudError as ex:
            print(
                f"Got error ({ex}) May be transient issue due to service account still initializing. Trying again in 5 seconds..."
            )
        time.sleep(5)
    raise Exception("10 failed attempts. Aborting")


def create_service_account(project, name):
    if name is None:
        name = f"hermit-{random_string(10).lower()}"

    username = os.getlogin()
    print(f'Creating service account "{name}" in project "{project}"...')
    gcp.gcloud(
        [
            "iam",
            "service-accounts",
            "create",
            name,
            "--project",
            project,
            "--display-name",
            f"Service account for hermit (v{__version__}, created by {username})",
        ]
    )
    service_account_name = f"{name}@{project}.iam.gserviceaccount.com"

    _perform_grants(service_account_name, project)

    gcloud_config = gcp.gcloud_capturing_json_output(
        ["config", "list", "--format=json"]
    )
    user_account = gcloud_config["core"]["account"]

    print(
        f"Granting access so that {user_account} can impersonate service account {service_account_name}"
    )
    # this should allow the current user to impersonate this service account
    gcp.gcloud(
        [
            "iam",
            "service-accounts",
            "add-iam-policy-binding",
            service_account_name,
            "--member",
            f"user:{user_account}",
            f"--role=roles/iam.serviceAccountTokenCreator",
            "--project",
            project,
        ]
    )

    # This was an older comment:
    # TODO: If this throws a permission error, try again after executing:
    #   gcloud iam service-accounts add-iam-policy-binding PRIV_SA \
    #     --member=serviceAccount:CALLER_SA --role=roles/iam.serviceAccountTokenCreator --format=json
    # Curious that we might be able to do this grant two ways?

    # Permissions in GCP are "eventually consistent", which means we may need to wait
    # a minute or two before the permissions above will take effect. Poll for a bit until
    # it seems to be enforced.
    gcp.wait_for_impersonating_access_token_success(service_account_name)

    write_default_service_account(project, service_account_name)

    return service_account_name


def grant(service_account, project, role):
    gcp.gcloud(
        [
            "projects",
            "add-iam-policy-binding",
            project,
            "--member",
            f"serviceAccount:{service_account}",
            "--role",
            role,
        ]
    )


def add_command(subparser):
    def _create_service_account(args):
        create_service_account(args.project, args.name)

    parser = subparser.add_parser(
        "create", help="Create a new service account with the required permissions"
    )
    parser.set_defaults(func=_create_service_account)
    parser.add_argument(
        "project",
        help="The project within which to create the service account",
    )
