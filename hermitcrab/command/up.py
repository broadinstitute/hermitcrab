from ..ssh import get_pub_key
from .. import gcp
from ..config import get_instance_config, CONTAINER_SSHD_PORT, LONG_OPERATION_TIMEOUT
import tempfile
from ..tunnel import is_tunnel_running, stop_tunnel, start_tunnel
import textwrap
import pkg_resources


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


def create_instance(instance_config):
    ssh_pub_key = get_pub_key()

    suspend_on_idle = pkg_resources.resource_string(
        "hermitcrab", "deploy_scripts/suspend_on_idle.py"
    ).decode("utf8")

    with tempfile.NamedTemporaryFile("wt") as tmp:
        # write out cloudinit file
        tmp.write(
            f"""#cloud-config

users:
- name: ubuntu

bootcmd:
- fsck.ext4 -tvy /dev/sdb
- mkdir -p /mnt/disks/{instance_config.pd_name}
- mount -t ext4 /dev/sdb /mnt/disks/{instance_config.pd_name}
- mkdir -p /mnt/disks/{instance_config.pd_name}/home/ubuntu/.ssh
- chown 2000:2000 /mnt/disks/{instance_config.pd_name}/home/ubuntu
- chmod -R 700 /mnt/disks/{instance_config.pd_name}/home/ubuntu/.ssh
- chown -R 2000:2000 /mnt/disks/{instance_config.pd_name}/home/ubuntu/.ssh
- mount --bind /mnt/disks/{instance_config.pd_name}/home/ubuntu/ /home/ubuntu

write_files:
- path: /mnt/disks/{instance_config.pd_name}/home/ubuntu/.ssh/authorized_keys
  permissions: "0700"
  content: |
    {ssh_pub_key}
- path: /home/cloudservice/suspend_on_idle.py
  content: |
{textwrap.indent(suspend_on_idle, "    ")}
- path: /etc/systemd/system/container-sshd.service
  permissions: "0644"
  owner: root
  content: |
    [Unit]
    Description=Container which we can connect via ssh
    Wants=gcr-online.target
    After=gcr-online.target

    [Service]
    Environment="HOME=/home/cloudservice"
    ExecStartPre=/usr/bin/docker-credential-gcr configure-docker
    ExecStart=/usr/bin/docker run --rm --name=container-sshd -p{CONTAINER_SSHD_PORT}:22 -v /var/run/docker.sock:/var/run/docker.sock -v /mnt/disks/{instance_config.pd_name}/home/ubuntu:/home/ubuntu {instance_config.docker_image} /usr/sbin/sshd -D -e
    ExecStop=/usr/bin/docker stop container-sshd
    ExecStopPost=/usr/bin/docker rm container-sshd
- path: /etc/systemd/system/suspend-on-idle.service
  permissions: "0644"
  owner: root
  content: |
    [Unit]
    Description=Suspend when container is detected to be idle
    Wants=gcr-online.target
    After=gcr-online.target

    [Service]
    ExecStart=/usr/bin/python /home/cloudservice/suspend_on_idle.py 1 {instance_config.suspend_on_idle_timeout} {instance_config.name} {instance_config.zone} {instance_config.project}
runcmd:
  - 'usermod -u 2000 ubuntu'
  - 'groupmod -g 2000 ubuntu'
  - 'chown ubuntu:ubuntu /mnt/disks/{instance_config.pd_name}/home/ubuntu/.ssh/authorized_keys'
  - 'chmod 0666 /var/run/docker.sock'
  - systemctl daemon-reload
  - systemctl start container-sshd.service
  - systemctl start suspend-on-idle.service
"""
        )
        tmp.flush()

        cloudinit_path = tmp.name
        print(f"Creating new instance named {instance_config.name}...")
        gcp.gcloud(
            [
                "compute",
                "instances",
                "create",
                instance_config.name,
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
            ],
            timeout=LONG_OPERATION_TIMEOUT,
        )


def up(name: str):
    instance_config = get_instance_config(name)

    # check again just in case something has changed since we created this config. Shouldn't really be
    # needed, but hopefully this check is fairly cheap.
    gcp.ensure_access_to_docker_image(
        instance_config.service_account, instance_config.docker_image
    )

    status = gcp.get_instance_status(
        instance_config.name,
        instance_config.zone,
        instance_config.project,
        one_or_none=True,
    )

    if status is None:
        create_instance(instance_config)
    elif status == "RUNNING":
        print(f"Instance {instance_config.name} is already running.")
    elif status == "SUSPENDED":
        resume_instance(instance_config)
    else:
        raise Exception(
            "Instance status is {status}, and this tool doesn't know what to do with that status."
        )

    if is_tunnel_running(instance_config.name):
        stop_tunnel(instance_config.name)

    start_tunnel(
        instance_config.name,
        instance_config.zone,
        instance_config.project,
        instance_config.local_port,
    )


def add_command(subparser):
    def _up(args):
        up(args.name)

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
