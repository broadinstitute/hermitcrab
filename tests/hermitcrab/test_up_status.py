import typing
import pytest
from hermitcrab.errors import UserError

log_updates = [
    """Starting cloudinit bootcmd...
Starting check filesystem /dev/disk/by-id/google-test-miniwdl-pd
fsck from util-linux 2.38.1
/dev/sdb: clean, 219827/13107200 files, 13578676/52428800 blocks
Mounting /dev/disk/by-id/google-test-miniwdl-pd as /mnt/disks/test-miniwdl-pd
Setting up ubuntu home directory permissions...
Mounting home directory into place...
Starting up services...
Configuring default registries....
WARNING: A long list of credential helpers may cause delays running 'docker build'.
We recommend passing the registry names via the --registries flag for the specific registries you are using
Adding config for all GCR registries.
/home/cloudservice/.docker/config.json configured to use this credential helper for GCR registries
Cloudinit runcmd complete.
Unable to find image 'us.gcr.io/depmap-omics/hermit-dev-env:v1' locally
v1: Pulling from depmap-omics/hermit-dev-env
""",
    """dbf6a9befcde: Pulling fs layer
d6b748fe7fad: Pulling fs layer
3f6b49d80f24: Pulling fs layer
f58ce966cd39: Pulling fs layer
089ba640f011: Pulling fs layer
6b22df04d12c: Pulling fs layer
01dcbecd78e4: Pulling fs layer
40a3ebe5ad01: Pulling fs layer
5fc4c2d637fa: Pulling fs layer
9f37869d1686: Pulling fs layer
0832c10da011: Pulling fs layer
dbf6a9befcde: Waiting
d6b748fe7fad: Waiting
8792a6636857: Pulling fs layer
6b22df04d12c: Waiting
3f6b49d80f24: Waiting
01dcbecd78e4: Waiting
f58ce966cd39: Waiting
089ba640f011: Waiting
40a3ebe5ad01: Waiting
5fc4c2d637fa: Waiting
0832c10da011: Waiting
8792a6636857: Waiting
9f37869d1686: Waiting
dbf6a9befcde: Verifying Checksum
dbf6a9befcde: Download complete
3f6b49d80f24: Verifying Checksum
3f6b49d80f24: Download complete
d6b748fe7fad: Verifying Checksum
d6b748fe7fad: Download complete
f58ce966cd39: Verifying Checksum
f58ce966cd39: Download complete
6b22df04d12c: Verifying Checksum
6b22df04d12c: Download complete
01dcbecd78e4: Download complete
089ba640f011: Verifying Checksum
089ba640f011: Download complete
dbf6a9befcde: Pull complete
5fc4c2d637fa: Verifying Checksum
5fc4c2d637fa: Download complete
9f37869d1686: Verifying Checksum
9f37869d1686: Download complete
0832c10da011: Verifying Checksum
0832c10da011: Download complete
40a3ebe5ad01: Verifying Checksum
40a3ebe5ad01: Download complete
8792a6636857: Verifying Checksum
8792a6636857: Download complete
d6b748fe7fad: Pull complete
3f6b49d80f24: Pull complete
f58ce966cd39: Pull complete
089ba640f011: Pull complete
6b22df04d12c: Pull complete
01dcbecd78e4: Pull complete
40a3ebe5ad01: Pull complete
5fc4c2d637fa: Pull complete
9f37869d1686: Pull complete
0832c10da011: Pull complete
8792a6636857: Pull complete
""",
    """Digest: sha256:52150323a61388610ad57bafb3003d960cff2517ef88f14caa84fea1ed37f308
Status: Downloaded newer image for us.gcr.io/depmap-omics/hermit-dev-env:v1
Server listening on 0.0.0.0 port 3022.
Server listening on :: port 3022.
kex_exchange_identification: Connection closed by remote host
Connection closed by 35.235.245.130 port 44405
kex_exchange_identification: Connection closed by remote host
Connection closed by 35.235.245.129 port 39757
kex_exchange_identification: Connection closed by remote host
Connection closed by 35.235.245.128 port 35851
kex_exchange_identification: Connection closed by remote host
Connection closed by 35.235.245.130 port 32949
""",
]

import hermitcrab.gcp
import hermitcrab.command.up
from unittest.mock import MagicMock
import time


def test_get_status_from_log():
    assert (
        False,
        [
            "Starting check filesystem",
            "Pulling from depmap-omics/hermit-dev-env",
        ],
    ) == hermitcrab.command.up.get_status_from_log(log_updates[0])
    assert (False, []) == hermitcrab.command.up.get_status_from_log(log_updates[1])
    assert (
        True,
        [
            "Status: Downloaded newer image for us.gcr.io/depmap-omics/hermit-dev-env:v1",
            "Server listening on 0.0.0.0 port 3022.",
        ],
    ) == hermitcrab.command.up.get_status_from_log(log_updates[2])


def test_status_updates(monkeypatch):
    output_index = 0

    def _mock_gcloud_capturing_output(*args, **kwargs):
        nonlocal output_index
        output_index += 1
        output = ""
        for i in range(output_index):
            if i < len(log_updates):
                output += log_updates[i]
        return output, ""

    monkeypatch.setattr(
        hermitcrab.gcp, "gcloud_capturing_output", _mock_gcloud_capturing_output
    )

    monkeypatch.setattr(time, "sleep", lambda x: None)

    output = []

    def capture_output(text: str):
        output.append(text)

    hermitcrab.command.up.wait_for_instance_start(
        MagicMock(),
        verbose=False,
        timeout=10 * 60,
        output_callback=(typing.cast(typing.Any, capture_output)),
    )

    assert output == [
        "[from /var/log/hermit.log] Starting check filesystem",
        "[from /var/log/hermit.log] Pulling from depmap-omics/hermit-dev-env",
        "[from /var/log/hermit.log] Status: Downloaded newer image for us.gcr.io/depmap-omics/hermit-dev-env:v1",
        "[from /var/log/hermit.log] Server listening on 0.0.0.0 port 3022.",
    ]


fsck_log_messages = [
    """
Starting cloudinit bootcmd...
Starting check filesystem /dev/disk/by-id/google-test-miniwdl-pd
fsck from util-linux 2.38.1
1 0 1600 /dev/sdb
1 1 1600 /dev/sdb
1 2 1600 /dev/sdb
1 3 1600 /dev/sdb
""",
    """1 123 1600 /dev/sdb
1 124 1600 /dev/sdb
1 125 1600 /dev/sdb
1 126 1600 /dev/sdb
1 127 1600 /dev/sdb
""",
    """5 3198 3200 /dev/sdb
5 3199 3200 /dev/sdb
5 3200 3200 /dev/sdb
/dev/sdb: 219827/13107200 files (5.2% non-contiguous), 13578676/52428800 blocks
Finished checking filesystem /dev/disk/by-id/google-test-miniwdl-pd
Mounting /dev/disk/by-id/google-test-miniwdl-pd as /mnt/disks/test-miniwdl-pd
Setting up ubuntu home directory permissions...
Mounting home directory into place...
""",
]


def test_fsck_progress_from_log():
    assert (
        False,
        [
            "Starting check filesystem",
            "Progress (Phase 1): 0%",
        ],
    ) == hermitcrab.command.up.get_status_from_log(fsck_log_messages[0])

    assert (
        False,
        [
            "Starting check filesystem",
            "Progress (Phase 1): 7%",
        ],
    ) == hermitcrab.command.up.get_status_from_log("".join(fsck_log_messages[0:2]))

    assert (
        False,
        ["Starting check filesystem", "Finished checking filesystem"],
    ) == hermitcrab.command.up.get_status_from_log("".join(fsck_log_messages))


missing_filesystem_log_msgs = [
    """Starting cloudinit bootcmd...
Starting check filesystem /dev/disk/by-id/google-temp-3
""",
    """fsck from util-linux 2.38.1
/dev/sdb:
The superblock could not be read or does not describe a valid ext2/ext3/ext4
filesystem.  If the device is valid and it really contains an ext2/ext3/ext4
""",
    """filesystem (and not swap or ufs or something else), then the superblock
is corrupt, and you might try running e2fsck with an alternate superblock:
    e2fsck -b 8193 <device>
 or
    e2fsck -b 32768 <device>

Finished checking filesystem /dev/disk/by-id/google-temp-3
Mounting /dev/disk/by-id/google-temp-3 as /mnt/disks/temp-3
+ echo 'initial mount state'
initial mount state
+ mount
/dev/mapper/vroot on / type ext2 (ro,relatime)
devtmpfs on /dev type devtmpfs (rw,nosuid,noexec,relatime,size=16432644k,nr_inodes=4108161,mode=755)
proc on /proc type proc (rw,nosuid,nodev,noexec,relatime)
sysfs on /sys type sysfs (rw,nosuid,nodev,noexec,relatime)
securityfs on /sys/kernel/security type securityfs (rw,nosuid,nodev,noexec,relatime)
tmpfs on /dev/shm type tmpfs (rw,nosuid,nodev,noexec)""",
    """
devpts on /dev/pts type devpts (rw,nosuid,noexec,relatime,gid=5,mode=620,ptmxmode=000)
tmpfs on /run type tmpfs (rw,nosuid,nodev,size=6574508k,nr_inodes=819200,mode=755)
""",
]


def test_missing_filesystem_log():
    assert (
        False,
        [
            "Starting check filesystem",
        ],
    ) == hermitcrab.command.up.get_status_from_log(missing_filesystem_log_msgs[0])

    with pytest.raises(UserError):
        hermitcrab.command.up.get_status_from_log(
            "".join(missing_filesystem_log_msgs[0:2])
        )


bad_image_log = [
    """Starting cloudinit bootcmd...
Starting check filesystem /dev/disk/by-id/google-test-miniwdl-pd
fsck from util-linux 2.38.1
/dev/sdb: clean, 467176/13107200 files, 47294363/52428800 blocks
Finished checking filesystem /dev/disk/by-id/google-test-miniwdl-pd
Mounting /dev/disk/by-id/google-test-miniwdl-pd as /mnt/disks/test-miniwdl-pd
Finished hermit VM setup
+ echo 'initial mount state'
initial mount state
+ mount
/dev/mapper/vroot on / type ext2 (ro,relatime)
devtmpfs on /dev type devtmpfs (rw,nosuid,noexec,relatime,size=16432648k,nr_inodes=4108162,mode=755)
proc on /proc type proc (rw,nosuid,nodev,noexec,relatime)
sysfs on /sys type sysfs (rw,nosuid,nodev,noexec,relatime)
securityfs on /sys/kernel/security type securityfs (rw,nosuid,nodev,noexec,relatime)
tmpfs on /dev/shm type tmpfs (rw,nosuid,nodev,noexec)
devpts on /dev/pts type devpts (rw,nosuid,noexec,relatime,gid=5,mode=620,ptmxmode=000)
tmpfs on /run type tmpfs (rw,nosuid,nodev,size=6574508k,nr_inodes=819200,mode=755)
cgroup2 on /sys/fs/cgroup type cgroup2 (rw,nosuid,nodev,noexec,relatime,nsdelegate,memory_recursiveprot)
pstore on /sys/fs/pstore type pstore (rw,nosuid,nodev,noexec,relatime)
bpf on /sys/fs/bpf type bpf (rw,nosuid,nodev,noexec,relatime,mode=700)
tmpfs on /etc/machine-id type tmpfs (ro,size=6574508k,nr_inodes=819200,mode=755)
systemd-1 on /proc/sys/fs/binfmt_misc type autofs (rw,relatime,fd=31,pgrp=1,timeout=0,minproto=5,maxproto=5,direct,pipe_ino=3560)
hugetlbfs on /dev/hugepages type hugetlbfs (rw,nosuid,nodev,relatime,pagesize=2M)
mqueue on /dev/mqueue type mqueue (rw,nosuid,nodev,noexec,relatime)
tmpfs on /mnt/disks type tmpfs (rw,relatime,size=256k,mode=755)
debugfs on /sys/kernel/debug type debugfs (rw,nosuid,nodev,noexec,relatime,gid=605,mode=750)
tracefs on /sys/kernel/tracing type tracefs (rw,nosuid,nodev,noexec,relatime)
efivarfs on /sys/firmware/efi/efivars type efivarfs (rw,nosuid,nodev,noexec,relatime)
fusectl on /sys/fs/fuse/connections type fusectl (rw,nosuid,nodev,noexec,relatime)
configfs on /sys/kernel/config type configfs (rw,nosuid,nodev,noexec,relatime)
overlayfs on /etc type overlay (rw,relatime,lowerdir=/etc,upperdir=/tmp/etc_overlay/etc,workdir=/tmp/etc_overlay/.work,uuid=on)
/dev/sda8 on /usr/share/oem type ext4 (ro,nosuid,nodev,noexec,relatime)
/dev/sda1 on /mnt/stateful_partition type ext4 (rw,nosuid,nodev,noexec,relatime,commit=30)
/dev/sda1 on /home type ext4 (rw,nosuid,nodev,noexec,relatime,commit=30)
/dev/sda1 on /var type ext4 (rw,nosuid,nodev,noexec,relatime,commit=30)
/dev/sda1 on /var/lib/containerd type ext4 (rw,nosuid,nodev,relatime,commit=30)
tmpfs on /var/lib/cloud type tmpfs (rw,nosuid,nodev,relatime,size=2048k,mode=755)
/dev/sda1 on /var/lib/docker type ext4 (rw,nosuid,nodev,relatime,commit=30)
/dev/sda1 on /var/lib/google type ext4 (rw,nosuid,nodev,relatime,commit=30)
/dev/sda1 on /var/lib/toolbox type ext4 (rw,nodev,relatime,commit=30)
/dev/nvme0n1 on /mnt/disks/local-ssd-0 type ext4 (rw,relatime)
/dev/nvme0n1 on /tmp type ext4 (rw,relatime)
/dev/sdb on /mnt/disks/test-miniwdl-pd type ext4 (rw,relatime)
+ echo 'Setting up ubuntu home directory permissions...'
Setting up ubuntu home directory permissions...
+ usermod -u 2000 ubuntu
usermod: no changes
+ groupmod -g 2000 ubuntu
+ chown 2000:2000 /mnt/disks/test-miniwdl-pd/home/ubuntu
+ chmod -R 700 /mnt/disks/test-miniwdl-pd/home/ubuntu/.ssh
+ chown -R 2000:2000 /mnt/disks/test-miniwdl-pd/home/ubuntu/.ssh
+ echo 'Mounting home directory into place...'
Mounting home directory into place...
+ mount --bind /mnt/disks/test-miniwdl-pd/home/ubuntu/ /home/ubuntu
+ chown ubuntu:ubuntu /mnt/disks/test-miniwdl-pd/home/ubuntu/.ssh/authorized_keys
+ chmod 0666 /var/run/docker.sock
+ echo 'Starting up services...'
Starting up services...
+ systemctl daemon-reload
+ systemctl restart docker
+ systemctl start container-sshd.service
Configuring supplied registries....
Adding config for registries: us-central1-docker.pkg.dev
/home/cloudservice/.docker/config.json configured to use this credential helper for GCR registries
+ systemctl start suspend-on-idle.service
+ echo 'final mount state'
final mount state
+ mount
/dev/mapper/vroot on / type ext2 (ro,relatime)
devtmpfs on /dev type devtmpfs (rw,nosuid,noexec,relatime,size=16432648k,nr_inodes=4108162,mode=755)
proc on /proc type proc (rw,nosuid,nodev,noexec,relatime)
sysfs on /sys type sysfs (rw,nosuid,nodev,noexec,relatime)
securityfs on /sys/kernel/security type securityfs (rw,nosuid,nodev,noexec,relatime)
tmpfs on /dev/shm type tmpfs (rw,nosuid,nodev,noexec)
devpts on /dev/pts type devpts (rw,nosuid,noexec,relatime,gid=5,mode=620,ptmxmode=000)
tmpfs on /run type tmpfs (rw,nosuid,nodev,size=6574508k,nr_inodes=819200,mode=755)
cgroup2 on /sys/fs/cgroup type cgroup2 (rw,nosuid,nodev,noexec,relatime,nsdelegate,memory_recursiveprot)
pstore on /sys/fs/pstore type pstore (rw,nosuid,nodev,noexec,relatime)
bpf on /sys/fs/bpf type bpf (rw,nosuid,nodev,noexec,relatime,mode=700)
tmpfs on /etc/machine-id type tmpfs (ro,size=6574508k,nr_inodes=819200,mode=755)
systemd-1 on /proc/sys/fs/binfmt_misc type autofs (rw,relatime,fd=31,pgrp=1,timeout=0,minproto=5,maxproto=5,direct,pipe_ino=3560)
hugetlbfs on /dev/hugepages type hugetlbfs (rw,nosuid,nodev,relatime,pagesize=2M)
mqueue on /dev/mqueue type mqueue (rw,nosuid,nodev,noexec,relatime)
tmpfs on /mnt/disks type tmpfs (rw,relatime,size=256k,mode=755)
debugfs on /sys/kernel/debug type debugfs (rw,nosuid,nodev,noexec,relatime,gid=605,mode=750)
tracefs on /sys/kernel/tracing type tracefs (rw,nosuid,nodev,noexec,relatime)
efivarfs on /sys/firmware/efi/efivars type efivarfs (rw,nosuid,nodev,noexec,relatime)
fusectl on /sys/fs/fuse/connections type fusectl (rw,nosuid,nodev,noexec,relatime)
configfs on /sys/kernel/config type configfs (rw,nosuid,nodev,noexec,relatime)
overlayfs on /etc type overlay (rw,relatime,lowerdir=/etc,upperdir=/tmp/etc_overlay/etc,workdir=/tmp/etc_overlay/.work,uuid=on)
/dev/sda8 on /usr/share/oem type ext4 (ro,nosuid,nodev,noexec,relatime)
/dev/sda1 on /mnt/stateful_partition type ext4 (rw,nosuid,nodev,noexec,relatime,commit=30)
/dev/sda1 on /home type ext4 (rw,nosuid,nodev,noexec,relatime,commit=30)
/dev/sda1 on /var type ext4 (rw,nosuid,nodev,noexec,relatime,commit=30)
/dev/sda1 on /var/lib/containerd type ext4 (rw,nosuid,nodev,relatime,commit=30)
tmpfs on /var/lib/cloud type tmpfs (rw,nosuid,nodev,relatime,size=2048k,mode=755)
/dev/sda1 on /var/lib/docker type ext4 (rw,nosuid,nodev,relatime,commit=30)
/dev/sda1 on /var/lib/google type ext4 (rw,nosuid,nodev,relatime,commit=30)
/dev/sda1 on /var/lib/toolbox type ext4 (rw,nodev,relatime,commit=30)
/dev/nvme0n1 on /mnt/disks/local-ssd-0 type ext4 (rw,relatime)
/dev/nvme0n1 on /tmp type ext4 (rw,relatime)
/dev/sdb on /mnt/disks/test-miniwdl-pd type ext4 (rw,relatime)
/dev/sdb on /home/ubuntu type ext4 (rw,relatime)
+ echo 'hermit-setup.sh complete'
""",
    """hermit-setup.sh complete
Unable to find image 'ubuntu:latest' locally
latest: Pulling from library/ubuntu
b08e2ff4391e: Pulling fs layer
b08e2ff4391e: Waiting
b08e2ff4391e: Download complete
b08e2ff4391e: Pull complete
Digest: sha256:440dcf6a5640b2ae5c77724e68787a906afb8ddee98bf86db94eea8528c2c076
Status: Downloaded newer image for ubuntu:latest
docker: Error response from daemon: failed to create task for container: failed to create shim task: OCI runtime create failed: runc create failed: unable to start container process: error during container init: exec: "/usr/sbin/sshd": stat /usr/sbin/sshd: no such file or directory: unknown.
Error response from daemon: No such container: container-sshd
Configuring supplied registries....
Adding config for registries: us-central1-docker.pkg.dev
/home/cloudservice/.docker/config.json configured to use this credential helper for GCR registries
docker: Error response from daemon: failed to create task for container: failed to create shim task: OCI runtime create failed: runc create failed: unable to start container process: error during container init: exec: "/usr/sbin/sshd": stat /usr/sbin/sshd: no such file or directory: unknown.
Error response from daemon: No such container: container-sshd
Configuring supplied registries....
Adding config for registries: us-central1-docker.pkg.dev
/home/cloudservice/.docker/config.json configured to use this credential helper for GCR registries
docker: Error response from daemon: failed to create task for container: failed to create shim task: OCI runtime create failed: runc create failed: unable to start container process: error during container init: exec: "/usr/sbin/sshd": stat /usr/sbin/sshd: no such file or directory: unknown.
Error response from daemon: No such container: container-sshd
Configuring supplied registries....
Adding config for registries: us-central1-docker.pkg.dev
/home/cloudservice/.docker/config.json configured to use this credential helper for GCR registries
docker: Error response from daemon: failed to create task for container: failed to create shim task: OCI runtime create failed: runc create failed: unable to start container process: error during container init: exec: "/usr/sbin/sshd": stat /usr/sbin/sshd: no such file or directory: unknown.
Error response from daemon: No such container: container-sshd
Configuring supplied registries....
Adding config for registries: us-central1-docker.pkg.dev
/home/cloudservice/.docker/config.json configured to use this credential helper for GCR registries
docker: Error response from daemon: failed to create task for container: failed to create shim task: OCI runtime create failed: runc create failed: unable to start container process: error during container init: exec: "/usr/sbin/sshd": stat /usr/sbin/sshd: no such file or directory: unknown.
Error response from daemon: No such container: container-sshd
Configuring supplied registries....
Adding config for registries: us-central1-docker.pkg.dev
/home/cloudservice/.docker/config.json configured to use this credential helper for GCR registries
docker: Error response from daemon: failed to create task for container: failed to create shim task: OCI runtime create failed: runc create failed: unable to start container process: error during container init: exec: "/usr/sbin/sshd": stat /usr/sbin/sshd: no such file or directory: unknown.
Error response from daemon: No such container: container-sshd
Configuring supplied registries....
Adding config for registries: us-central1-docker.pkg.dev
/home/cloudservice/.docker/config.json configured to use this credential helper for GCR registries
docker: Error response from daemon: failed to create task for container: failed to create shim task: OCI runtime create failed: runc create failed: unable to start container process: error during container init: exec: "/usr/sbin/sshd": stat /usr/sbin/sshd: no such file or directory: unknown.
Error response from daemon: No such container: container-sshd
Configuring supplied registries....
Adding config for registries: us-central1-docker.pkg.dev
/home/cloudservice/.docker/config.json configured to use this credential helper for GCR registries
docker: Error response from daemon: failed to create task for container: failed to create shim task: OCI runtime create failed: runc create failed: unable to start container process: error during container init: exec: "/usr/sbin/sshd": stat /usr/sbin/sshd: no such file or directory: unknown.
Error response from daemon: No such container: container-sshd
Configuring supplied registries....
Adding config for registries: us-central1-docker.pkg.dev
/home/cloudservice/.docker/config.json configured to use this credential helper for GCR registries
docker: Error response from daemon: failed to create task for container: failed to create shim task: OCI runtime create failed: runc create failed: unable to start container process: error during container init: exec: "/usr/sbin/sshd": stat /usr/sbin/sshd: no such file or directory: unknown.
Error response from daemon: No such container: container-sshd""",
]


def test_bad_image():
    assert (
        False,
        ["Starting check filesystem", "Finished checking filesystem"],
    ) == hermitcrab.command.up.get_status_from_log(bad_image_log[0])

    with pytest.raises(UserError):
        hermitcrab.command.up.get_status_from_log("".join(bad_image_log[0:2]))
