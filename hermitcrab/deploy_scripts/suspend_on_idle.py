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
    )


def poll(poll_frequency, activity_timeout, name, zone, project):
    last_bytes_transmitted = None
    last_activity = time.time()
    while True:
        bytes_transmitted = get_bytes_transmitted()
        if last_bytes_transmitted != bytes_transmitted:
            last_bytes_transmitted = bytes_transmitted
            last_activity = time.time()
            log.info("%s", f"active (last_bytes_transmitted={last_bytes_transmitted})")
        elapsed_since_activity = time.time() - last_activity
        if elapsed_since_activity > activity_timeout:
            suspend_instance(name, zone, project)
            log.info("Suspend complete")
            time.sleep(5 * 60)
            # this is likely after the VM has been resumed
            log.info("Resuming polling...")
        time.sleep(poll_frequency)
    log.info(
        "%s",
        f"{elapsed_since_activity} seconds elapsed since last sign of activity. Suspending...",
    )


def suspend_instance(name, zone, project):
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

    if return_code != 0:
        log.info(
            f"Return code was non-zero {return_code}. Unable to suspend, so trying shutdown --poweroff instead"
        )
        return_code = subprocess.run(["shutdown", "--poweroff"]).returncode
        log.info(f"return code = {return_code}")


def get_bytes_transmitted():
    output = subprocess.check_output(["iptables", "-nvxL", "DOCKER-USER"])
    lines = output.decode("utf8").split("\n")

    def parse():
        if len(lines) != 4:
            print(f"expected 4 lines but was {len(lines)}")
            return (
                None  # could not parse because the output should always be three lines
            )
        m = re.match("\\s+(\\d+)\\s+(\\d+)\\s+.", lines[2])
        if m is None:
            return None  # again, don't know what this is
        return int(m.group(2))

    result = parse()
    if result is None:
        print(f"Could not parse: {output}")
    return result


# sudo iptables -nvxL DOCKER-USER
# Chain DOCKER-USER (1 references)
#    pkts      bytes target     prot opt in     out     source               destination
#      61    12560 RETURN     all  --  *      *       0.0.0.0/0            0.0.0.0/0

if __name__ == "__main__":
    main()
