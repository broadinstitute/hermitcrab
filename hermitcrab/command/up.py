from ..ssh import get_pub_key
from ..gcp import gcloud
from ..config import get_instance_config, CONTAINER_SSHD_PORT
import tempfile
from ..tunnel import is_tunnel_running, stop_tunnel, start_tunnel


def up(name: str):
    ssh_pub_key = get_pub_key()
    instance_config = get_instance_config(name)
    assert instance_config is not None, f"Could not file config for {name}"

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

write_files:
- path: /mnt/disks/{instance_config.pd_name}/home/ubuntu/.ssh/authorized_keys
  permissions: "0700"
  content: |
    {ssh_pub_key}
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
    ExecStart=/usr/bin/docker run --rm --name=container-sshd -p{CONTAINER_SSHD_PORT}:22 -v /mnt/disks/{instance_config.pd_name}/home/ubuntu:/home/ubuntu {instance_config.docker_image} /usr/sbin/sshd -D -e
    ExecStop=/usr/bin/docker stop container-sshd
    ExecStopPost=/usr/bin/docker rm container-sshd
runcmd:
  - 'usermod -u 2000 ubuntu'
  - 'groupmod -g 2000 ubuntu'
  - 'chown ubuntu:ubuntu /mnt/disks/{instance_config.pd_name}/home/ubuntu/.ssh/authorized_keys'
  - 'chmod 0666 /var/run/docker.sock'
  - systemctl daemon-reload
  - systemctl start container-sshd.service
"""
        )
        tmp.flush()

        cloudinit_path = tmp.name
        print(f"Creating new instance named {instance_config.name}...")
        gcloud(
            [
                "compute",
                "instances",
                "create",
                instance_config.name,
                "--image-family=cos-stable",
                "--image-project=cos-cloud",
                f"--zone={instance_config.zone}",
                f"--project={instance_config.project}",
                f"--machine-type={instance_config.machine_type}",
                f"--metadata-from-file=user-data={cloudinit_path}",
                f"--disk=name={instance_config.pd_name},device-name={instance_config.pd_name},auto-delete=no",
            ]
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
