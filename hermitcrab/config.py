import os
import json
from typing import Dict, List
import sqlite3

from dataclasses import dataclass, asdict

CONTAINER_SSHD_PORT = 3022
LONG_OPERATION_TIMEOUT = 60 * 5


class NoDefaultServiceAccount(Exception):
    pass


@dataclass
class InstanceConfig:
    name: str
    zone: str
    project: str
    machine_type: str
    docker_image: str
    pd_name: str
    local_port: int
    service_account: str
    boot_disk_size_in_gb: int
    suspend_on_idle_timeout: int = 30
    local_ssd_count: int = 0


@dataclass
class MinInstanceConfig:
    name: str
    zone: str
    project: str
    pd_name: str


def get_home_config_dir():
    home_dir = os.environ.get("HOME")
    assert home_dir is not None
    return os.path.join(home_dir, ".hermit")


def get_instance_config_dir():
    return os.path.join(get_home_config_dir(), "instances")


def get_assumption_cache():
    return os.path.join(get_home_config_dir(), "assumptions")


def get_tunnel_status_dir(create_if_missing=False):
    path = os.path.join(get_home_config_dir(), "tunnels")
    if create_if_missing:
        ensure_dir_exists(path)
    return path


def ensure_dir_exists(config_dir):
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)


def record_assumption(name):
    filename = get_assumption_cache()
    new_db = not os.path.exists(filename)
    connection = sqlite3.connect(filename)
    if new_db:
        connection.execute(
            "CREATE TABLE assumption (name varchar(100), primary key (name))"
        )
    cur = connection.cursor()
    cur.execute("insert into assumption ( name ) values ( ? )", [name])
    connection.commit()
    connection.close()


def is_assumption_present(name):
    filename = get_assumption_cache()
    if not os.path.exists(filename):
        return False
    connection = sqlite3.connect(filename)
    cur = connection.cursor()
    cur.execute("select name from assumption where name = ?", [name])
    rows = cur.fetchall()
    connection.close()
    return len(rows) > 0


import re

INSTANCE_NAME_REGEX = "^[a-z0-9-]+.json$"


def get_instance_names() -> List[str]:
    names = set()
    config_dir = get_instance_config_dir()
    if os.path.exists(config_dir):
        for filename in os.listdir(config_dir):
            if re.match(INSTANCE_NAME_REGEX, filename):
                name = filename[: -len(".json")]  # drop the extension
                config = get_min_instance_config(name)
                names.add(config.name)
    return sorted(names)


def _read_instance_config_dict(name):
    config_dir = get_instance_config_dir()
    config_filename = os.path.join(config_dir, f"{name}.json")

    with open(config_filename, "rt") as fd:
        config_dict = json.load(fd)

    if "boot_disk_size_in_gb" not in config_dict:
        config_dict["boot_disk_size_in_gb"] = 10

    return config_dict


def config_exists(name):
    config_dir = get_instance_config_dir()
    config_filename = os.path.join(config_dir, f"{name}.json")

    return os.path.exists(config_filename)


def get_min_instance_config(name):
    config_dict = _read_instance_config_dict(name)

    min_config_dict = {}
    for prop in ["name", "zone", "project", "pd_name"]:
        min_config_dict[prop] = config_dict[prop]

    return MinInstanceConfig(**min_config_dict)


def get_instance_configs():
    configs = []
    for name in get_instance_names():
        config = get_instance_config(name)
        configs.append(config)
    return configs


def get_instance_config(name):
    config_dict = _read_instance_config_dict(name)

    if "service_account" not in config_dict:
        raise Exception(
            f'Configuration {name} is missing a value for "service_account". (This is a recent change to hermit)'
        )

    return InstanceConfig(**config_dict)


def delete_instance_config(name: str):
    config_dir = get_instance_config_dir()
    assert name != "default"

    # check to see if this name is what default is pointing to
    if config_exists("default"):
        default_config = get_instance_config("default")
        if default_config.name == name:
            os.unlink(os.path.join(config_dir, "default.json"))

    # now delete the config under its read name
    config_filename = os.path.join(config_dir, f"{name}.json")
    assert os.path.exists(config_filename)
    os.unlink(config_filename)


def write_instance_config(config: InstanceConfig):
    config_dir = get_instance_config_dir()
    config_filename = os.path.join(config_dir, f"{config.name}.json")

    ensure_dir_exists(config_dir)
    config_dict = asdict(config)
    with open(config_filename, "wt") as fd:
        fd.write(json.dumps(config_dict, indent=2, sort_keys=True))


def set_default_instance_config(name):
    config_dir = get_instance_config_dir()
    config_filename = os.path.join(config_dir, f"{name}.json")

    print(f"Setting {name} as the 'default' instance config")
    if os.path.exists(os.path.join(config_dir, "default.json")):
        os.unlink(os.path.join(config_dir, "default.json"))
    os.symlink(
        os.path.relpath(config_filename, config_dir),
        os.path.join(config_dir, "default.json"),
    )


def _get_default_service_account_filename(project):
    return os.path.join(get_home_config_dir(), "service-accounts", project)


def write_default_service_account(project, name):
    fn = _get_default_service_account_filename(project)
    parent_dir = os.path.dirname(fn)
    if not os.path.exists(parent_dir):
        os.makedirs(parent_dir)
    with open(fn, "wt") as fd:
        fd.write(name)


def read_default_service_account(project):
    fn = _get_default_service_account_filename(project)
    if not os.path.exists(fn):
        raise NoDefaultServiceAccount()
    with open(fn, "rt") as fd:
        return fd.read().strip()
