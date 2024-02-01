from glob import glob
import json


def test_check_gcloud_calls():
    # look at the recordings and make sure every gcloud command has a "--project" and "--zone" argument
    # otherwise, gcloud was using the default and that might mean the test passed when it was recorded,
    # but the command isn't going to use the right project/zone when run by someone else.
    for cassette_name in glob("cassettes/*.json"):
        with open(cassette_name, "rt") as fd:
            recording = json.load(fd)
        for cmd, arg, result in recording:
            gcloud_args = " ".join(arg["args"][0])

            if gcloud_args.startswith("config"):
                continue

            assert "--project" in gcloud_args
            if not gcloud_args.startswith("compute firewall-rules"):
                assert "--zone" in gcloud_args
