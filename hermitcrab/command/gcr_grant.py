from .. import gcp
from ..config import get_instance_config


def gcr_grant(project, instance_name, needs_write_access):
    if needs_write_access:
        role = "roles/storage.objectAdmin"
    else:
        role = "roles/storage.objectViewer"

    config = get_instance_config(instance_name)
    assert config is not None
    bucket = f"us.artifacts.{project}.appspot.com"

    print(f"Granting {role} on GS bucket {bucket} to {config.service_account} ")
    gcp.gcloud(
        [
            "projects",
            "add-iam-policy-binding",
            project,
            f"--member=serviceAccount:{config.service_account}",
            f"--role={role}",
        ]
    )

    wait_for_access(config.service_account, bucket)


import time


def wait_for_access(service_account, bucket, retry_delay=5, max_wait=60 * 5):
    print(
        "Waiting for grant to take effect... (May take awhile, but this only needs to happen once)"
    )
    start = time.time()
    attempts = 0
    while True:
        attempts += 1

        try:
            gcp.gcloud(
                [
                    "storage",
                    "ls",
                    f"gs://{bucket}",
                    f"--impersonate-service-account={service_account}",
                ]
            )
            break
        except gcp.GCloudError as ex:
            if (time.time() - start) > max_wait:
                raise Exception(
                    f"Failed to verify that permissions are set up for impersonification after {attempts} checks. Aborting"
                )

            time.sleep(retry_delay)


def add_command(subparser):
    def _gcr_grant(args):
        gcr_grant(args.project, args.name, args.push)

    parser = subparser.add_parser(
        "gcr-grant",
        help="grant access to pull (and optionally push) to GCR docker repo in specified project",
    )
    parser.set_defaults(func=_gcr_grant)
    parser.add_argument(
        "project",
        help="The project containing the GCR repo that you want the instance to have access to",
    )
    parser.add_argument(
        "name",
        help="The name of the instance that you want to have access to use the GCR repo",
        nargs="?",
        default="default",
    )
    parser.add_argument(
        "--push",
        help="If specified, will grant access to push to repo as well as read from repo",
        action="store_true",
    )
