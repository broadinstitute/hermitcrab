from ..ssh import get_pub_key
from .. import gcp
from ..config import (
    get_instance_config,
    get_instance_configs,
    CONTAINER_SSHD_PORT,
    LONG_OPERATION_TIMEOUT,
    set_default_instance_config,
)
import tempfile
from ..tunnel import is_tunnel_running, stop_tunnel, start_tunnel
import pkg_resources
from ..ssh import update_ssh_config
import time
import re
import io
import yaml
from ..config import InstanceConfig
from .. import __version__
import os

# change the live-restore flag to false because its incompatible with swarm mode
# (which is required by miniwdl). The other options were the values in the file before.
docker_daemon_config = """
{
	"live-restore": false,
	"log-opts": {
                "tag": "{{.Name}}"
        },
	"storage-driver": "overlay2",
	"mtu": 1460
}
"""


def resume_instance(instance_config):
    print(f"Resuming suspended instance named {instance_config.name}...")
    gcp.gcloud(
        [
            "compute",
            "instances",
            "resume",
            instance_config.name,
            f"--zone={instance_config.zone}",
            f"--project={instance_config.project}",
        ],
        timeout=LONG_OPERATION_TIMEOUT,
    )


def _create_bootcmd(instance_config: InstanceConfig):
    bootcmd = [
        "echo in-bootcmd",
        'echo "Starting cloudinit bootcmd..." >> /var/log/hermit.log',
        "mount",
        "umount /tmp",
    ]
    # if we have no local ssd drives, use /var/tmp for /tmp
    if instance_config.local_ssd_count == 0:
        bootcmd.append("mount --bind /var/tmp /tmp")
    else:
        for i in range(instance_config.local_ssd_count):
            bootcmd.extend(
                [
                    f"mkfs -t ext4 /dev/disk/by-id/google-local-nvme-ssd-{i}",
                    f"mkdir -p /mnt/disks/local-ssd-{i}",
                    f"mount -t ext4 /dev/disk/by-id/google-local-nvme-ssd-{i} /mnt/disks/local-ssd-{i}",
                ]
            )
            # if we're using at least one local ssd drive, mount it at /tmp
            if i == 0:
                bootcmd.extend(
                    [
                        f"mkdir /mnt/disks/local-ssd-{i}/tmp",
                        f"chmod 1777 /mnt/disks/local-ssd-{i}/tmp",
                        f"mount --bind /mnt/disks/local-ssd-{i}/tmp /tmp",
                    ]
                )

    bootcmd.extend(
        [
            f"echo in-bootcmd-after-tmp-remount",
            f"mount",
            f'echo "Checking filesystem /dev/disk/by-id/google-{instance_config.pd_name}" >> /var/log/hermit.log',
            f"fsck -C 1 -a /dev/disk/by-id/google-{instance_config.pd_name} >> /var/log/hermit.log",
            f'echo "Finished checking filesystem /dev/disk/by-id/google-{instance_config.pd_name}" >> /var/log/hermit.log',
            f"mkdir -p /mnt/disks/{instance_config.pd_name}",
            f'echo "Mounting /dev/disk/by-id/google-{instance_config.pd_name}" as /mnt/disks/{instance_config.pd_name} >> /var/log/hermit.log',
            f"mount -t ext4 /dev/disk/by-id/google-{instance_config.pd_name} /mnt/disks/{instance_config.pd_name}",
            f"mkdir -p /mnt/disks/{instance_config.pd_name}/home/ubuntu/.ssh",
        ]
    )

    return bootcmd


def _create_cloud_config(instance_config: InstanceConfig):
    ssh_pub_key = get_pub_key()

    suspend_on_idle = pkg_resources.resource_string(
        "hermitcrab", "deploy_scripts/suspend_on_idle.py"
    ).decode("utf8")

    hermit_setup = f"""
set -ex
echo "initial mount state"
mount
echo "Setting up ubuntu home directory permissions..."
usermod -u 2000 ubuntu
groupmod -g 2000 ubuntu
chown 2000:2000 /mnt/disks/{instance_config.pd_name}/home/ubuntu
chmod -R 700 /mnt/disks/{instance_config.pd_name}/home/ubuntu/.ssh
chown -R 2000:2000 /mnt/disks/{instance_config.pd_name}/home/ubuntu/.ssh
echo "Mounting home directory into place..."
mount --bind /mnt/disks/{instance_config.pd_name}/home/ubuntu/ /home/ubuntu
chown ubuntu:ubuntu /mnt/disks/{instance_config.pd_name}/home/ubuntu/.ssh/authorized_keys
chmod 0666 /var/run/docker.sock
echo "Starting up services..."
systemctl daemon-reload
systemctl restart docker
systemctl start container-sshd.service
systemctl start suspend-on-idle.service
echo "final mount state"
mount
echo "hermit-setup.sh complete"
"""

    cloud_config = {
        "bootcmd": _create_bootcmd(instance_config),
        "write_files": [
            {
                "path": f"/mnt/disks/{instance_config.pd_name}/home/ubuntu/.ssh/authorized_keys",
                "permissions": "0700",
                "content": ssh_pub_key,
            },
            {
                "path": "/home/cloudservice/suspend_on_idle.py",
                "content": suspend_on_idle,
            },
            {"path": "/home/cloudservice/hermit-setup.sh", "content": hermit_setup},
            {
                "path": "/home/cloudservice/setup_firewall",
                "content": f"""
# Create a chain for tracking traffic to ssh in container
iptables -N CONTAINER_SSH
iptables -I INPUT -j CONTAINER_SSH
iptables -A CONTAINER_SSH -p tcp --dport {CONTAINER_SSHD_PORT}
iptables -A INPUT -p tcp --dport {CONTAINER_SSHD_PORT} -j ACCEPT
""",
            },
            {
                "path": "/etc/systemd/system/config-firewall.service",
                "permissions": "0644",
                "owner": "root",
                "content": f"""
[Unit]
Description=Configures the host firewall

[Service]
Type=oneshot
RemainAfterExit=true
ExecStart=/bin/sh /home/cloudservice/setup_firewall
""",
            },
            {
                "path": "/etc/systemd/system/container-sshd.service",
                "permissions": "0644",
                "owner": "root",
                "content": f"""
[Unit]
Description=Container which we can connect via ssh
Wants=gcr-online.target config-firewall.service
After=gcr-online.target config-firewall.service

[Service]
Environment="HOME=/home/cloudservice"
StandardOutput=append:/var/log/hermit.log
ExecStartPre=/usr/bin/docker-credential-gcr configure-docker --registries us-central1-docker.pkg.dev
ExecStart=/usr/bin/docker run --rm --name=container-sshd --network=host -v /var/run/docker.sock:/var/run/docker.sock -v /tmp:/tmp -v /mnt/disks/{instance_config.pd_name}/home/ubuntu:/home/ubuntu {instance_config.docker_image} /usr/sbin/sshd -D -e -p {CONTAINER_SSHD_PORT}
ExecStop=/usr/bin/docker stop container-sshd
ExecStopPost=/usr/bin/docker rm container-sshd
Restart=always
""",
            },
            {
                "path": "/etc/systemd/system/suspend-on-idle.service",
                "permissions": "0644",
                "owner": "root",
                "content": f"""
[Unit]
Description=Suspend when container is detected to be idle
Wants=gcr-online.target
After=gcr-online.target

[Service]
ExecStart=/usr/bin/python /home/cloudservice/suspend_on_idle.py 1 {instance_config.suspend_on_idle_timeout} {instance_config.name} {instance_config.zone} {instance_config.project} {CONTAINER_SSHD_PORT}
Restart=always""",
            },
            {
                "path": "/etc/docker/daemon.json",
                "permissions": "0644",
                "owner": "root",
                "content": docker_daemon_config,
            },
        ],
        "users": [{"name": "ubuntu"}],
        "runcmd": [
            "echo in-runcmd",
            "bash /home/cloudservice/hermit-setup.sh >> /var/log/hermit.log 2>&1",
        ],
    }

    return cloud_config


def _dict_to_yaml_str(value):
    buf = io.StringIO()
    yaml.dump(value, buf)
    return buf.getvalue()


def create_instance(instance_config: InstanceConfig):
    username = os.getlogin()

    cloud_config = _create_cloud_config(instance_config)

    with tempfile.NamedTemporaryFile("wt") as tmp:
        # write out cloudinit file
        tmp.write("#cloud-config\n")
        tmp.write(_dict_to_yaml_str(cloud_config))
        tmp.flush()

        cloudinit_path = tmp.name
        print(f"Creating new instance named {instance_config.name}...")
        create_options = [
            f"--description=hermit v{__version__} VM started user {username}",
            "--image-family=cos-stable",
            "--image-project=cos-cloud",
            f"--boot-disk-size={instance_config.boot_disk_size_in_gb}GB",
            f"--zone={instance_config.zone}",
            f"--project={instance_config.project}",
            f"--machine-type={instance_config.machine_type}",
            f"--metadata-from-file=user-data={cloudinit_path}",
            f"--disk=name={instance_config.pd_name},device-name={instance_config.pd_name},auto-delete=no",
            # use scopes that are equivilent to 'default' from https://cloud.google.com/sdk/gcloud/reference/compute/instances/create#--scopes
            # but also add compute-rw so that the instance can suspend itself down when idle.
            f"--scopes=storage-ro,logging-write,monitoring-write,pubsub,service-management,service-control,trace,compute-rw",
            f"--service-account={instance_config.service_account}",
        ]

        for _ in range(instance_config.local_ssd_count):
            create_options.extend(["--local-ssd=interface=nvme"])

        gcp.gcloud(
            [
                "compute",
                "instances",
                "create",
                instance_config.name,
            ]
            + create_options,
            timeout=LONG_OPERATION_TIMEOUT,
        )


def up(name: str, verbose: bool):
    instance_config = get_instance_config(name)

    if not gcp.has_access_to_docker_image(
        instance_config.service_account, instance_config.docker_image
    ):
        print(
            gcp.get_grant_instructions(
                instance_config.service_account, instance_config.docker_image
            )
        )
        return 1

    status = gcp.get_instance_status(
        instance_config.name,
        instance_config.zone,
        instance_config.project,
        one_or_none=True,
    )

    if status == "TERMINATED":
        raise Exception(
            "Found existing stopped instance. You'll need to manually delete it before proceeding"
        )

    if status is None:
        gcp.log_info(f"Creating instance")
        create_instance(instance_config)
    elif status == "RUNNING":
        gcp.log_info(f"Instance is running")
        print(f"Instance {instance_config.name} is already running.")
    elif status == "SUSPENDED":
        gcp.log_info(f"Instance is suspended")
        resume_instance(instance_config)
    else:
        raise Exception(
            f"Instance status is {status}, and this tool doesn't know what to do with that status."
        )

    gcp.log_info(f"Waiting for instance to start")
    wait_for_instance_start(instance_config, verbose, timeout=60 * 60)

    if is_tunnel_running(instance_config.name):
        gcp.log_info(f"Stopping tunnel process")
        stop_tunnel(instance_config.name)
    else:
        gcp.log_info(f"Tunnel is not running running")

    gcp.log_info(f"Starting tunnel")
    start_tunnel(
        instance_config.name,
        instance_config.zone,
        instance_config.project,
        instance_config.local_port,
    )

    gcp.log_info(f"Updating ssh config")
    update_ssh_config(get_instance_configs())

    gcp.log_info(f"setting default instance config to {instance_config.name}")
    set_default_instance_config(instance_config.name)


def wait_for_instance_start(
    instance_config: InstanceConfig,
    verbose: bool,
    timeout: float,
    output_callback=print,
    poll_frequency=1,
):
    # the lines of status we've already shown to the user
    printed_status = set()
    previous_printed = ""

    start_time = time.time()
    # breakpoint()
    while True:
        stdout, stderr = gcp.gcloud_capturing_output(
            [
                "compute",
                "ssh",
                instance_config.name,
                f"--project",
                instance_config.project,
                f"--zone",
                instance_config.zone,
                "--tunnel-through-iap",
                f"--command",
                "cat /var/log/hermit.log",
            ],
            ignore_error=True,
            retries_on_timeout=10,
        )

        if stderr != "":
            gcp.log_info(f"stderr from compute ssh poll command: {stderr}")

        if stdout == "":
            if "Connection refused" in stderr:
                if verbose:
                    gcp.log_info(f"Got connection refused: {stderr}")
                    output_callback(f"Can't connect yet, will retry... ({stderr})")
        else:
            # if log file does not exist yet, stderr will contain error and stdout will
            # be blank.

            if verbose:
                new_output = stdout[len(previous_printed) :]
                output_callback(new_output, end="")
                previous_printed = stdout

            is_ssh_ready, status = get_status_from_log(stdout)

            # show the user and status updates we haven't already shown
            for line in status:
                if line not in printed_status:
                    output_callback(f"[from /var/log/hermit.log] {line}")
                    printed_status.add(line)

            if is_ssh_ready:
                break

        elapsed = time.time() - start_time
        if elapsed > timeout:
            raise TimeoutError(
                f"{elapsed} seconds elapsed waiting for log entry saying ssh is listening"
            )

        if verbose:
            print(f"sleeping for {poll_frequency} seconds")
        time.sleep(poll_frequency)


def get_status_from_log(log_content):
    "Given the contents of /var/logs/hermit.log, return a tuple of (ssh_ready:bool, summary:List[str])"

    ssh_ready = False
    status = []

    check_fs_m = re.search("^(Checking filesystem)", log_content, re.MULTILINE)
    if check_fs_m:
        status.append(check_fs_m.group(1))

    finished_check_fs_m = re.search(
        "^(Finished checking filesystem)", log_content, re.MULTILINE
    )
    if finished_check_fs_m:
        status.append(finished_check_fs_m.group(1))

    if check_fs_m and not finished_check_fs_m:
        progress_matches = re.findall(
            "^(\\d+) (\\d+) (\\d+) (\\S+)$", log_content, re.MULTILINE
        )  # 5 3199 3200 /dev/sdb
        if len(progress_matches) > 0:
            last_progress_match = progress_matches[-1]
            phase = int(last_progress_match[0])
            current_value = int(last_progress_match[1])
            max_value = int(last_progress_match[2])
            status.append(
                f"Progress (Phase {phase}): {int(current_value*100/max_value)}%"
            )

    m = re.search("(Pulling from \\S+)$", log_content, re.MULTILINE)
    if m:
        status.append(m.group(1))

    m = re.search("^(Server listening on 0.0.0.0.*)$", log_content, re.MULTILINE)
    if m:
        status.append(m.group(1))
        ssh_ready = True

    return ssh_ready, status


def add_command(subparser):
    def _up(args):
        up(args.name, args.verbose)

    parser = subparser.add_parser(
        "up", help="Start a compute instance based on the named configuration"
    )
    parser.set_defaults(func=_up)
    parser.add_argument(
        "name",
        help="The name to use when creating instance",
        nargs="?",
        default="default",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="If set, will print more logging information showing the server coming online",
    )
