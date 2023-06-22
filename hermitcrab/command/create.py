import re
import tempfile
from .. import gcp

from ..config import (
    get_instance_config,
    get_instance_configs,
    config_exists,
    write_instance_config,
    get_instance_names,
    InstanceConfig,
    CONTAINER_SSHD_PORT,
    LONG_OPERATION_TIMEOUT,
    set_default_instance_config,
)
from ..ssh import update_ssh_config
from . import create_service_account


def create_volume(
    pd_name,
    drive_size,
    drive_type,
    name,
    service_account,
    zone,
    project,
    machine_type="n2-standard-2",
):
    disk_status = gcp.gcloud_capturing_json_output(
        [
            "compute",
            "disks",
            "list",
            f"--filter=name={pd_name}",
            f"--zones={zone}",
            "--format=json",
            f"--project={project}",
        ],
    )
    assert len(disk_status) == 0, f"Disk {pd_name} already exists"

    existing_status = gcp.get_instance_status(name, zone, project, one_or_none=True)
    assert (
        existing_status is None
    ), f"Expected there to be no instance with name {name}, but found one with status {existing_status}"

    print(f"Creating persistent disk named {pd_name}")
    # gcloud compute disks create test-create-vol --size=50 --zone=us-central1-a --type=pd-standard
    gcp.gcloud(
        [
            "compute",
            "disks",
            "create",
            pd_name,
            f"--size={drive_size}",
            f"--zone={zone}",
            f"--type={drive_type}",
            f"--project={project}",
        ],
        timeout=LONG_OPERATION_TIMEOUT,
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

        print(f"Creating filesystem on {pd_name} (using a temp instance named {name})")

        cloudinit_path = tmp.name
        gcp.gcloud(
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
                f"--service-account={service_account}",
            ],
            timeout=LONG_OPERATION_TIMEOUT,
        )

    gcp.wait_for_instance_status(name, zone, project, "TERMINATED")

    gcp.gcloud(
        [
            "compute",
            "instances",
            "delete",
            name,
            f"--zone={zone}",
            f"--project={project}",
        ]
    )


def ensure_firewall_setup(project):
    # Add rule to allow connections from IAP tunnel. See https://cloud.google.com/iap/docs/using-tcp-forwarding
    IAP_TUNNEL_IP_RANGE = "35.235.240.0/20"

    firewall_settings = gcp.gcloud_capturing_json_output(
        [
            "compute",
            "firewall-rules",
            "list",
            "--filter=name=allow-altssh-ingress-from-iap",
            "--format=json",
            f"--project={project}",
        ],
    )
    if len(firewall_settings) == 0:
        # create rule if it's not present
        print("Adding firewall rule to allow connections from IAP")
        gcp.gcloud(
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


def find_unused_port():
    used_ports = []
    for name in get_instance_names():
        config = get_instance_config(name)
        used_ports.append(config.local_port)
    if len(used_ports) > 0:
        return max(used_ports) + 1
    return 3022


def create(
    name: str,
    drive_size: int,
    drive_type: str,
    machine_type: str,
    service_account: str,
    project: str,
    zone: str,
    docker_image: str,
    pd_name: str,
    local_port: int,
    idle_timeout: int,
    boot_disk_size_in_gb: int,
):
    assert zone
    assert project
    assert pd_name

    gcp.ensure_access_to_docker_image(service_account, docker_image)

    assert not config_exists(name), f"{name} appears to already have a config stored"

    ensure_firewall_setup(project)

    create_volume(pd_name, drive_size, drive_type, name, service_account, zone, project)
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
            suspend_on_idle_timeout=idle_timeout,
            service_account=service_account,
            boot_disk_size_in_gb=boot_disk_size_in_gb,
        )
    )

    update_ssh_config(get_instance_configs())
    set_default_instance_config(name)


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

        gcloud_defaults = gcp.gcloud_capturing_json_output(
            ["config", "list", "--format=json"]
        )
        if args.project is None:
            project = gcloud_defaults.get("core", {}).get("project")
            print(f"Using project {project} (default according to gcloud)")
        else:
            project = args.project

        assert (
            project is not None
        ), "no default project in gcloud config, so specified the project with the --project parameter"

        if args.zone is None:
            zone = gcloud_defaults.get("compute", {}).get("zone")
            print(f"Using zone {zone} (default according to gcloud)")
        else:
            zone = args.zone

        assert (
            zone is not None
        ), "no default zone in gcloud config, so specified the project with the --zone parameter"

        if args.local_port is None:
            local_port = find_unused_port()
        else:
            local_port = args.local_port

        if args.service_account:
            service_account = args.service_account
        else:
            service_account = (
                create_service_account.get_or_create_default_service_account(project)
            )

        create(
            args.name,
            args.disk_size,
            args.disk_type,
            args.machine_type,
            service_account,
            project,
            zone,
            args.docker_image,
            pd_name,
            local_port,
            args.idle_timeout,
            args.boot_disk_size_in_gb,
        )

    parser = subparser.add_parser("create", help="Create a new instance config")
    parser.set_defaults(func=_create)
    parser.add_argument(
        "name",
        help="The name to use when creating instance",
    )
    parser.add_argument(
        "docker_image",
        help="Name of the docker image to use",
    )
    parser.add_argument(
        "--disk-size",
        default=200,
        help="Size of the home directory volume in GBs (Defaults to 200GB if not specified)",
        dest="disk_size",
    )
    parser.add_argument(
        "--boot-disk-size",
        default=50,
        dest="boot_disk_size_in_gb",
        help="The size of the boot volume (which needs to be large enough to hold all docker images and containers)",
        type=int,
    )
    parser.add_argument(
        "--disk-type",
        default="pd-standard",
        dest="disk_type",
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
        default=None,
        help="The port on localhost that will be used to establish a tunnel to the instance. If not specified will attempt to pick a port after 3022 not assigned to any other instances",
    )
    parser.add_argument(
        "--idle-timeout",
        dest="idle_timeout",
        type=int,
        default=30,
        help="The number of minutes the machine appears idle before it is suspended",
    )
    parser.add_argument(
        "--service-account",
        dest="service_account",
        help="If specified, the id of the service account to assign to the host as the default service account",
    )
