import subprocess
import re
import time
import argparse
import os

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
    suspend_fail_count = 0
    last_bytes_transmitted = None
    last_activity = time.time()
    while True:
        bytes_transmitted = get_bytes_transmitted(port)
        if last_bytes_transmitted != bytes_transmitted:
            last_bytes_transmitted = bytes_transmitted
            last_activity = time.time()
            log.info("%s", f"active (last_bytes_transmitted={last_bytes_transmitted})")

            # reset if there's some activity. Only want to count the number of failed suspends since we've decided that we're idle
            suspend_fail_count = 0
        elapsed_since_activity = time.time() - last_activity
        if elapsed_since_activity > activity_timeout:
            log.info(
                "%s",
                f"{elapsed_since_activity} seconds elapsed since last sign of activity. Suspending...",
            )
            successful_suspend = suspend_instance(name, zone, project)
            log.info(
                f"Suspend is over. Waiting for {activity_timeout/60} minutes before polling again"
            )
            time.sleep(activity_timeout)
            # this is likely after the VM has been resumed but ...
            # it's been observed that the suspend command often reports failure even though the vm successfully suspended.
            # I don't have a reliable way of telling whether it worked or not. (Specificly, it gets a timeout trying to read the response
            # to the suspend request, because while it was
            # reading, the VM got suspended. ) In the event that suspend _really_ is broken, we want to shutdown as that's
            # safer then leaving the machine run forever. So, let's go with a heuristic of, if it fails repeatedly then shutdown.

            if not successful_suspend:
                log.info(
                    "Suspend command reportedly failed -- but not sure if that's true. Incrementing fail count"
                )
                suspend_fail_count += 1

                if suspend_fail_count > 10:
                    log.info(
                        f"suspending failed {suspend_fail_count} times. Shutting down as a last resort"
                    )
                    _shutdown()

            log.info("Resuming polling...")
        time.sleep(poll_frequency)


def _shutdown():
    return_code = subprocess.run(["shutdown", "--poweroff"]).returncode
    log.info(f"return code = {return_code}")


def suspend_instance(name, zone, project):
    has_ssd = os.path.exists("/mnt/disks/local-ssd-0") or os.path.exists(
        "/mnt/disks/local-ssd"
    )
    cmd = [
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

    if has_ssd:
        cmd.append("--discard-local-ssd=false")

    return_code = subprocess.run(cmd).returncode

    return return_code == 0


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
