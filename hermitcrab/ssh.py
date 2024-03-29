from hermitcrab import config
from typing import List, Sequence
import shutil
import time
import os
import tempfile


def replace_if_changed(dest_filename: str, content: str):
    if not os.path.exists(dest_filename):
        file_existed = False
        prev_content = ""
    else:
        file_existed = True
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
        if file_existed:
            shutil.copy(dest_filename, backup_filename)
        os.rename(tmpname, dest_filename)


START_MARKER = "### AUTOMATICALLY ADDED BY HERMITCRAB START ###\n"
END_MARKER = "### AUTOMATICALLY ADDED BY HERMITCRAB END ###\n"


def remove_section(content: str, start_marker: str, end_marker: str):
    if start_marker not in content:
        return content
    start_index = content.index(start_marker)
    end_index = content.index(end_marker) + len(end_marker)

    return content[:start_index] + content[end_index:]


def get_ssh_dir():
    return os.path.join(os.environ["HOME"], ".ssh")


def get_ssh_config_path():
    return os.path.join(get_ssh_dir(), "config")


def update_ssh_config(configs: Sequence[config.InstanceConfig]):
    # because default is an alias, we get dups in this sequence. Dedup them by name
    by_name = {c.name: c for c in configs}

    # sort so that we get a deterministic order
    configs = sorted(by_name.values(), key=lambda x: x.name)

    ssh_config_path = get_ssh_config_path()

    if os.path.exists(ssh_config_path):
        with open(ssh_config_path, "rt") as fd:
            config_content = fd.read()
    else:
        config_content = ""

    config_content = remove_section(config_content, START_MARKER, END_MARKER)

    # make sure that the configuration content ends with a newline. If it doesn't
    # when we concatenate, we'll add the START_MARKER on the end of a config statement
    # which ssh does not like and results in an error like ".ssh/config line 4: keyword identityfile extra arguments at end of line"

    if config_content != "" and not config_content.endswith("\n"):
        config_content = "\n"

    if len(configs) > 0:
        new_section = [
            """#
# This section may be rewritten by 'hermit' so avoid making 
# manual edits here. They will be lost next time hermit updates this file.
#
"""
        ]
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
    for name in ["id_rsa.pub", "id_ed25519.pub"]:
        path = os.path.join(get_ssh_dir(), name)
        if os.path.exists(path):
            with open(path, "rt") as fd:
                return fd.read()

    raise Exception("could not find ssh pub key")
