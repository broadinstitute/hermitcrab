import os
import json
from typing import Dict
from .gcp import get_default_service_account

from dataclasses import dataclass, asdict

CONTAINER_SSHD_PORT = 3022
LONG_OPERATION_TIMEOUT = 60 * 5


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


def get_home_config_dir():
    home_dir = os.environ.get("HOME")
    assert home_dir is not None
    return os.path.join(home_dir, ".hermit")


def get_instance_config_dir():
    return os.path.join(get_home_config_dir(), "instances")


def get_tunnel_status_dir(create_if_missing=False):
    path = os.path.join(get_home_config_dir(), "tunnels")
    if create_if_missing:
        ensure_dir_exists(path)
    return path


def ensure_dir_exists(config_dir):
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)


def get_instance_configs() -> Dict[str, InstanceConfig]:
    configs = {}
    config_dir = get_instance_config_dir()
    if os.path.exists(config_dir):
        for filename in os.listdir(config_dir):
            if filename.endswith(".json"):
                name = filename[: -len(".json")]  # drop the extension
                configs[name] = get_instance_config(name)
    if "default" in configs:
        del configs["default"]
    return configs


def get_instance_config(name):
    config_dir = get_instance_config_dir()
    config_filename = os.path.join(config_dir, f"{name}.json")

    if not os.path.exists(config_filename):
        return None

    with open(config_filename, "rt") as fd:
        config_dict = json.load(fd)

    if "service_account" not in config_dict:
        print(
            f'Configuration {config_filename} is missing a value for "service_account". (This is a recent change to hermit). Attempting to find default Compute Engine service account and will use that. Add this to the config manually to avoid this message in the future.'
        )
        service_account = get_default_service_account(config_dict["project"])
        print(f"Identified {service_account} as the default service account.")
        config_dict["service_account"] = service_account

    if "boot_disk_size_in_gb" not in config_dict:
        config_dict["boot_disk_size_in_gb"] = 10
    # ), f'Missing "service_account" field on config for {name}. This field was added to hermit recently and you will need to manually add it to {config_filename}.'

    return InstanceConfig(**config_dict)


def delete_instance_config(name: str):
    config_dir = get_instance_config_dir()
    assert name != "default"

    # check to see if this name is what default is pointing to
    default_config = get_instance_config("default")
    if default_config is not None and default_config.name == name:
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

    print(f"Setting {config.name} as the 'default' instance config")
    if os.path.exists(os.path.join(config_dir, "default.json")):
        os.unlink(os.path.join(config_dir, "default.json"))
    os.symlink(
        os.path.relpath(config_filename, config_dir),
        os.path.join(config_dir, "default.json"),
    )
