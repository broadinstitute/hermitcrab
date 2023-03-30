import subprocess
import time

def gcloud(args):
    for x in args:
        assert isinstance(x, str) or isinstance(x, int) or isinstance(x, float), f"{x} not an expected type"
    args = [str(x) for x in args]

    subprocess.check_call(["gcloud"]+args)

def get_instance_status(name, zone, project, one_or_none=False):
    status = gcloud(['compute', 'instances', 'list', 
                     f'--filter=name={name}', 
                     '--format=value(status)',
                     f'--zone={zone}',
                     f'--project={project}'], capture_stdout=True)
    if one_or_none:
        if status.strip() == "":
            return None
    assert len(status.strip().split("\n")) == 1, f"Expected one line of status but got {repr(status)}"
    return status.strip()

def wait_for_instance_status(name, zone, project, goal_status, max_time=5*60):
    prev_status = None
    start_time = time.time()
    while True:
        status = get_instance_status(name, zone, project)
        if status == goal_status:
            break
        if status != prev_status:
            print(f"status became {status}")
        assert time.time() - start_time < max_time, f"Was waiting for status to change to {goal_status} but more than {max_time} seconds elapsed"
        prev_status = status
        time.sleep(5)
