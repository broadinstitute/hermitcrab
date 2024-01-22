import subprocess
import re
import time
import argparse

# cmd to suspend: docker run google/cloud-sdk gcloud compute instances suspend {name} --zone {zone}
# but needs additional scopes/permissions. Create a service account for this? Actually just a broadening the scope looks sufficient
import logging

log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("poll_frequency", type=float)
    parser.add_argument("activity_timeout", type=float)
    parser.add_argument("name")
    parser.add_argument("zone")
    parser.add_argument("project")
    parser.add_argument("port")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    # fetch docker image at the beginning just to make sure it's successful and we don't wait until
    # we actually need it.
    subprocess.check_call(["docker", "pull", "google/cloud-sdk"])

    poll(
        args.poll_frequency * 60,
        args.activity_timeout * 60,
        args.name,
        args.zone,
        args.project,
        args.port,
    )


def poll(poll_frequency, activity_timeout, name, zone, project, port):
    last_bytes_transmitted = None
    last_activity = time.time()
    while True:
        bytes_transmitted = get_bytes_transmitted(port)
        if last_bytes_transmitted != bytes_transmitted:
            last_bytes_transmitted = bytes_transmitted
            last_activity = time.time()
            log.info("%s", f"active (last_bytes_transmitted={last_bytes_transmitted})")
        elapsed_since_activity = time.time() - last_activity
        if elapsed_since_activity > activity_timeout:
            log.info(
                "%s",
                f"{elapsed_since_activity} seconds elapsed since last sign of activity. Suspending...",
            )
            suspend_instance(name, zone, project)
            log.info("Suspend complete")
            time.sleep(5 * 60)
            # this is likely after the VM has been resumed
            log.info("Resuming polling...")
        time.sleep(poll_frequency)


def suspend_instance(name, zone, project):
    start_time = time.time()
    return_code = subprocess.run(
        [
            "docker",
            "run",
            "google/cloud-sdk",
            "gcloud",
            "compute",
            "instances",
            "suspend",
            name,
            "--zone",
            zone,
            "--project",
            project,
        ]
    ).returncode
    end_time = time.time()
    elapsed = end_time - start_time

    if elapsed > 10 * 60:
        # it's been observed that this command often reports failure even though the vm successfully suspended.
        # Specificly, it gets a timeout trying to read the response, because while it was
        # reading, the VM got suspended. This is a bit of a hack, but lets try to detect
        # this case by seeing how long that command took. If it took a _long_ time
        # it's probably because the machine was suspended and woke up much later
        log.info(
            f"Suspend command took {elapsed} secs to complete, probably suspended in the middle. (return_code={return_code})"
        )
        return_code = 0

    if return_code != 0:
        log.info(
            f"Return code was non-zero {return_code}. Unable to suspend, so trying shutdown --poweroff instead"
        )
        return_code = subprocess.run(["shutdown", "--poweroff"]).returncode
        log.info(f"return code = {return_code}")


def get_bytes_transmitted(port):
    output = subprocess.check_output(["iptables", "-nvxL", "CONTAINER_SSH"])
    lines = output.decode("utf8").split("\n")

    def parse():
        for line in lines:
            if (
                f"tcp dpt:{port}" in line
            ):  # find the line for the rule for traffic on the port
                m = re.match("\\s*(\\d+)\\s+(\\d+)\\s+.", line)
                if m is not None:
                    return int(m.group(2))
        return None  # could not find the rule

    result = parse()
    if result is None:
        print(f"Could not parse: {output}")
    return result


if __name__ == "__main__":
    main()
