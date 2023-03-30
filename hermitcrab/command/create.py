import re
import tempfile
from ..gcp import get_instance_status, gcloud, wait_for_instance_status
from ..config import (
    get_instance_config,
    get_instance_configs,
    write_instance_config,
    InstanceConfig,
    CONTAINER_SSHD_PORT,
)
from ..ssh import update_ssh_config
import json


def create_volume(
    pd_name, drive_size, drive_type, name, zone, project, machine_type="n2-standard-2"
):
    disk_json = json.loads(
        gcloud(
            [
                "compute",
                "disks",
                "list",
                f"--filter=name={pd_name}",
                f"--zones={zone}",
                "--format=json",
            ],
            capture_stdout=True,
        )
    )
    assert len(disk_json) == 0, f"Disk {pd_name} already exists"

    existing_status = get_instance_status(name, zone, project, one_or_none=True)
    assert (
        existing_status is None
    ), f"Expected there to be no instance with name {name}, but found one with status {existing_status}"

    # gcloud compute disks create test-create-vol --size=50 --zone=us-central1-a --type=pd-standard
    gcloud(
        [
            "compute",
            "disks",
            "create",
            pd_name,
            f"--size={drive_size}",
            f"--zone={zone}",
            f"--type={drive_type}",
        ]
    )

    with tempfile.NamedTemporaryFile("wt") as tmp:
        # write out cloudinit file
        tmp.write(
            """#cloud-config

bootcmd:
- mkfs /dev/sdb
- shutdown -h now
        """
        )
        tmp.flush()

        cloudinit_path = tmp.name
        gcloud(
            [
                "compute",
                "instances",
                "create",
                name,
                "--image-family=cos-stable",
                "--image-project=cos-cloud",
                f"--zone={zone}",
                f"--machine-type={machine_type}",
                f"--metadata-from-file=user-data={cloudinit_path}",
                f"--disk=name={pd_name},device-name={pd_name},auto-delete=no",
                f"--zone={zone}",
                f"--project={project}",
            ]
        )

    wait_for_instance_status(name, zone, project, "TERMINATED")

    gcloud(["compute", "instances", "delete", name])


def ensure_firewall_setup(project):
    # Add rule to allow connections from IAP tunnel. See https://cloud.google.com/iap/docs/using-tcp-forwarding
    IAP_TUNNEL_IP_RANGE = "35.235.240.0/20"

    firewall_settings_json = gcloud(
        [
            "compute",
            "firewall-rules",
            "list",
            "--filter=name=allow-altssh-ingress-from-iap",
            "--format=json",
            f"--project={project}",
        ],
        capture_stdout=True,
    )
    firewall_settings = json.loads(firewall_settings_json)
    if len(firewall_settings_json) == 0:
        # create rule if it's not present
        gcloud(
            [
                "compute",
                "firewall-rules",
                "create",
                "allow-altssh-ingress-from-iap",
                "--direction=INGRESS",
                "--action=allow",
                f"--rules=tcp:{CONTAINER_SSHD_PORT}",
                f"--source-ranges={IAP_TUNNEL_IP_RANGE}",
                f"--project={project}",
            ]
        )
    else:
        # some simple santity checks to make sure it's set the way we want
        assert len(firewall_settings) == 1
        rule = firewall_settings[0]
        assert rule["allowed"] == [
            {"IPProtocol": "tcp", "ports": [str(CONTAINER_SSHD_PORT)]}
        ]
        assert rule["direction"] == "INGRESS"
        assert rule["disabled"] == False
        assert rule["sourceRanges"] == [
            IAP_TUNNEL_IP_RANGE
        ]  # , f"expected {IAP_TUNNEL_IP_RANGE} but got {rule['sourceRanges']}"


def create(
    name: str,
    drive_size: int,
    drive_type: str,
    machine_type: str,
    project: str,
    zone: str,
    docker_image: str,
    pd_name: str,
    local_port: int,
):
    assert zone
    assert project
    assert pd_name

    assert (
        get_instance_config(name) is None
    ), f"{name} appears to already have a config stored"

    ensure_firewall_setup(project)

    create_volume(pd_name, drive_size, drive_type, name, zone, project)
    print(
        f"Successfully created {drive_size}GB filesystem on persistent disk {pd_name}"
    )

    write_instance_config(
        InstanceConfig(
            name=name,
            zone=zone,
            project=project,
            machine_type=machine_type,
            docker_image=docker_image,
            pd_name=pd_name,
            local_port=local_port,
        )
    )

    update_ssh_config(list(get_instance_configs().values()))


def assert_valid_gcp_name(description, name):
    m = re.match("[a-z0-9-]+", name)
    assert (
        m
    ), f"{description} {repr(name)} is not a valid name for GCP. Only lowercase letters, numbers and dashes are allowed"


def add_command(subparser):
    def _create(args):
        pd_name = args.pd_name
        if pd_name is None:
            pd_name = f"{args.name}-pd"

        assert_valid_gcp_name("instance name", args.name)
        assert_valid_gcp_name("persistent disk name", pd_name)

        assert args.zone, "zone must be specified"
        assert args.project, "project must be specified"

        create(
            args.name,
            args.drive_size,
            args.drive_type,
            args.machine_type,
            args.project,
            args.zone,
            args.docker_image,
            pd_name,
            args.local_port,
        )

    parser = subparser.add_parser("create", help="Create a new instance config")
    parser.set_defaults(func=_create)
    parser.add_argument(
        "name",
        help="The name to use when creating instance",
    )
    parser.add_argument(
        "drive_size",
        help="Size of the home directory volume in GBs",
    )
    parser.add_argument(
        "docker_image",
        help="Name of the docker image to use",
    )
    parser.add_argument(
        "--drive-type",
        default="pd-standard",
        dest="drive_type",
        help="The type of persistent disk to use for the home volume (see: https://cloud.google.com/compute/docs/disks )",
    )
    parser.add_argument(
        "--machine-type",
        default="n2-standard-2",
        dest="machine_type",
        help="The type of instance to create when bringing the instance up (see: https://cloud.google.com/compute/docs/machine-resource )",
    )
    parser.add_argument("--project")
    parser.add_argument("--zone")
    parser.add_argument(
        "--pd-name",
        default=None,
        dest="pd_name",
        help='What to name the persistent disk used for the home volume. ("NAME-pd" if not specified)',
    )
    parser.add_argument(
        "--local-port",
        dest="local_port",
        type=int,
        default=3022,
        help="The port on localhost that will be used to establish a tunnel to the instance.",
    )
