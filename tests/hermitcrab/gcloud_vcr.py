# Supporting code to record/playback calls to external/slow services to make tests faster
# in the spirit of VCR ( https://vcrpy.readthedocs.io/en/latest/ )

import pytest
import json

from dataclasses import dataclass
import time
from functools import wraps

from hermitcrab import tunnel
from hermitcrab import gcp


@dataclass
class Raised:
    raised: Exception

    def as_dict(self):
        return {"raised": self.raised}


@dataclass
class Returned:
    value: object

    def as_dict(self):
        return {"returned": self.value}


RECORDING = "recording"
PLAYBACK = "playback"
NONE = "none"
import re


class PlaybackError(Exception):
    pass


def _rewrite_metadata_param(args):
    new_args = []
    prefix = "--metadata-from-file=user-data="
    for arg in args:
        if arg.startswith(prefix):
            filename = arg[len(prefix) :]
            with open(filename, "rt") as fd:
                content = fd.read()
                # this content contains an key which needs to be replaced because
                # when we're playing back, we don't have access to the real key
                content = re.sub("ssh-rsa .+", "ssh-rsa X", content)

            new_args.append(f"{arg[:len(prefix)]}<{content}>")
        else:
            new_args.append(arg)
    return new_args


def _rewrite_call_info(function, parameters):
    if function == "gcloud":
        parameters["args"][0] = _rewrite_metadata_param(parameters["args"][0])
    return function, parameters


def make_recording_wrapper(f, record_callback):
    function_name = f.__name__

    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            ret = f(*args, **kwargs)
        except Exception as ex:
            record_callback(
                function_name, {"args": list(args), "kwargs": kwargs}, Raised(ex)
            )
            raise
        record_callback(
            function_name, {"args": list(args), "kwargs": kwargs}, Returned(ret)
        )
        return ret

    return wrapper


def make_playback_wrapper(f, vcr):
    _function_name = f.__name__

    @wraps(f)
    def wrapper(*args, **kwargs):
        function_name = _function_name

        next_fn, next_parameters, next_result = vcr.recording[vcr.current_call]
        vcr.current_call += 1

        parameters = _simplify_struct({"args": list(args), "kwargs": kwargs})
        function_name, parameters = vcr.rewrite_call(function_name, parameters)

        if next_fn != function_name:
            raise PlaybackError(
                f"Got a call to {function_name} when expecting a call to {next_fn}. This could be due to either non-determinism in test, or the recorded cassette is stale. Rerun test with --no-playback to re-record cassette."
            )
        if parameters != next_parameters:
            raise PlaybackError(
                f"Call to {function_name} had different parameters than expected. Expected: \n{json.dumps(next_parameters, indent=2)}\nActual call:\n{json.dumps(parameters, indent=2)}\n This could be due to either non-determinism in test, or the recorded cassette is stale. Rerun test with --no-playback to re-record cassette."
            )

        if isinstance(next_result, Raised):
            raise next_result.raised
        else:
            assert isinstance(next_result, Returned)
            return next_result.value

    return wrapper


def _simplify_struct(x):
    if isinstance(x, dict):
        return {k: _simplify_struct(v) for k, v in x.items()}
    elif isinstance(x, list):
        return [_simplify_struct(v) for v in x]
    else:
        assert (
            isinstance(x, str)
            or isinstance(x, int)
            or isinstance(x, float)
            or isinstance(x, bool)
            or x is None
        )
        return x


class VCR:
    def __init__(self, mode):
        self.mode = mode
        self.recording = []
        self.current_call = 0
        self.rewrite_call_info_callbacks = []

    def rewrite_call(self, function, parameters):
        for callbacks in self.rewrite_call_info_callbacks:
            function, parameters = callbacks(function, parameters)
        return function, parameters

    def record(self, function, parameters, result):
        operation = _simplify_struct([function, parameters, result.as_dict()])
        assert isinstance(operation, list)
        operation[0], operation[1] = self.rewrite_call(operation[0], operation[1])
        self.recording.append(operation)

    def write_recording(self, cassette_name):
        with open(cassette_name, "wt") as fd:
            fd.write(json.dumps(self.recording, indent=2))

    def read_recording(self, cassette_name):
        with open(cassette_name, "rt") as fd:
            r = json.load(fd)

        self.recording = []
        for fn, params, result in r:
            if "returned" in result:
                result = Returned(result["returned"])
            else:
                assert "raised" in result
                result = Raised(result["raised"])
            self.recording.append((fn, params, result))

    def is_recording(self):
        return self.mode == RECORDING

    def is_playback(self):
        return self.mode == PLAYBACK


def _get_test_name(request):
    test_class = request.cls
    if test_class:
        return "{}.{}".format(test_class.__name__, request.node.name)
    return request.node.name


import hermitcrab.command.create_service_account


def setup_vcr(monkeypatch, request, mode=None):
    if mode is None:
        if request.config.getoption("playback"):
            mode = PLAYBACK
        else:
            mode = RECORDING

    test_name = _get_test_name(request)

    # make sure we're consistently using the same service account
    monkeypatch.setattr(
        hermitcrab.command.create_service_account,
        "get_or_create_default_service_account",
        lambda project: "hermit-nrqacuv537@broad-achilles.iam.gserviceaccount.com",
    )

    cassette_name = f"cassettes/{test_name}.json"
    vcr = VCR(mode)
    vcr.rewrite_call_info_callbacks.append(_rewrite_call_info)

    if vcr.is_playback():
        vcr.read_recording(cassette_name)

    for fn in ["gcloud_capturing_json_output", "gcloud_in_background", "gcloud"]:
        if vcr.is_recording():
            monkeypatch.setattr(
                gcp, fn, make_recording_wrapper(getattr(gcp, fn), vcr.record)
            )
        else:
            assert vcr.is_playback()
            monkeypatch.setattr(gcp, fn, make_playback_wrapper(getattr(gcp, fn), vcr))

    monkeypatch.setattr(
        gcp, "sanity_check_docker_image", lambda service_account, docker_image: None
    )
    if vcr.is_playback():
        monkeypatch.setattr(time, "sleep", lambda x: None)
        monkeypatch.setattr(
            tunnel, "wait_for_proc_to_die_or_port_listening", lambda *args: None
        )

    return vcr, cassette_name


def teardown_vcr(vcr, cassette_name):
    if vcr.is_recording():
        vcr.write_recording(cassette_name)
