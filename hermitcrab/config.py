import os
import json

from dataclasses import dataclass, asdict

CONTAINER_SSHD_PORT=3022

@dataclass
class InstanceConfig:
    name: str
    zone: str
    project : str
    machine_type : str
    docker_image: str
    pd_name: str
    local_port: int

def get_instance_config_dir():
    home_dir = os.environ.get("HOME")
    assert home_dir is not None
    return os.path.join(home_dir, ".hermit", "instances")

def ensure_config_dirs_exists():
    config_dir = get_instance_config_dir()
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)

def get_instance_configs():
    configs = {}
    config_dir = get_instance_config_dir()
    for filename in os.listdir(config_dir):
        if filename.endswith(".json"):
            name = filename[:-len(".json")] # drop the extension
            configs[name] = get_instance_config(name)
    return configs

def get_instance_config(name):
    config_dir = get_instance_config_dir()
    config_filename = os.path.join(config_dir, name)

    if not os.path.exists(config_filename):
        return None
    
    with open(config_filename, "rt") as fd:
        config_dict = json.load(fd)

    return InstanceConfig(**config_dict)

def write_config(config):
    ensure_config_dirs_exists()

    config_dir = get_instance_config_dir()
    config_filename = os.path.join(config_dir, config.name)

    config_dict = asdict(config)
    with open(config_filename, "wt") as fd:
        fd.write(json.dumps(config_dict, indent=2, sort_keys=True))

    print(f"Setting {config.name} as the 'default' instance config")
    os.symlink(config_filename, os.path.join(config_dir, "default"))
