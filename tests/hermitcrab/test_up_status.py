log_updates = [
    """Starting cloudinit bootcmd...
Checking filesystem /dev/disk/by-id/google-test-miniwdl-pd
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


def test_get_status_from_log():
    assert (
        False,
        [
            "Checking filesystem",
            "Pulling from depmap-omics/hermit-dev-env",
        ],
    ) == hermitcrab.command.up.get_status_from_log(log_updates[0])
    assert (False, []) == hermitcrab.command.up.get_status_from_log(log_updates[1])
    assert (
        True,
        ["Server listening on 0.0.0.0 port 3022."],
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

    output = []

    def capture_output(text):
        output.append(text)

    hermitcrab.command.up.wait_for_instance_start(
        MagicMock(), verbose=False, timeout=10 * 60, output_callback=capture_output
    )

    assert output == [
        "[from /var/log/hermit.log] Checking filesystem",
        "[from /var/log/hermit.log] Pulling from depmap-omics/hermit-dev-env",
        "[from /var/log/hermit.log] Server listening on 0.0.0.0 port 3022.",
    ]


fsck_log_messages = [
    """
Starting cloudinit bootcmd...
Checking filesystem /dev/disk/by-id/google-test-miniwdl-pd
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
            "Checking filesystem",
            "Progress (Phase 1): 0%",
        ],
    ) == hermitcrab.command.up.get_status_from_log(fsck_log_messages[0])

    assert (
        False,
        [
            "Checking filesystem",
            "Progress (Phase 1): 7%",
        ],
    ) == hermitcrab.command.up.get_status_from_log("".join(fsck_log_messages[0:2]))

    assert (
        False,
        ["Checking filesystem", "Finished checking filesystem"],
    ) == hermitcrab.command.up.get_status_from_log("".join(fsck_log_messages))
