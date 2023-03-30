from hermitcrab import config
from typing import List, Sequence
import shutil
import time
import os
import tempfile


def replace_if_changed(dest_filename: str, content: str):
    if not os.path.exists(dest_filename):
        prev_content = ""
    else:
        with open(dest_filename, "rt") as fd:
            prev_content = fd.read()

    if prev_content != content:
        backup_filename = f"{dest_filename}.{int(time.time())}"
        print(f"Updating {dest_filename} after saving a backup named {backup_filename}")

        tmpfd, tmpname = tempfile.mkstemp(
            prefix="tmpconfig", dir=os.path.dirname(dest_filename), text=True
        )
        os.close(tmpfd)

        with open(tmpname, "wt") as fd:
            fd.write(content)

        # make a backup copy
        shutil.copy(dest_filename, backup_filename)
        os.rename(tmpname, dest_filename)


START_MARKER = "### AUTOMATICALLY ADDED BY HERMITCRAB TOOL START ###\n"
END_MARKER = "### AUTOMATICALLY ADDED BY HERMITCRAB TOOL END ###\n"


def remove_section(content: str, start_marker: str, end_marker: str):
    if start_marker not in content:
        return content
    start_index = content.index(start_marker)
    end_index = content.index(end_marker) + len(end_marker)

    return content[:start_index] + content[end_index:]


def update_ssh_config(configs: Sequence[config.InstanceConfig]):
    # sort so that we get a deterministic order
    configs = sorted(configs, key=lambda x: x.name)

    ssh_config_path = os.path.join(os.environ["HOME"], ".ssh", "config")

    with open(ssh_config_path, "rt") as fd:
        config_content = fd.read()

    config_content = remove_section(config_content, START_MARKER, END_MARKER)

    if len(configs) > 0:
        new_section = []
        for instance_config in configs:
            new_section.append(
                f"""Host {instance_config.name}
   Hostname localhost
   User ubuntu
   Port {instance_config.local_port}
   UserKnownHostsFile /dev/null
   StrictHostKeyChecking no

"""
            )
        config_content = (
            config_content + START_MARKER + ("".join(new_section)) + END_MARKER
        )

    replace_if_changed(ssh_config_path, config_content)


def get_pub_key():
    path = os.path.join(os.environ["HOME"], ".ssh", "id_rsa.pub")
    assert os.path.exists(path), f"Could not find ssh public key: {path}"
    with open(path, "rt") as fd:
        return fd.read()
