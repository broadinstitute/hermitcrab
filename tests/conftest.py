import pytest
from .hermitcrab.gcloud_vcr import setup_vcr, teardown_vcr;
from hermitcrab import config
from hermitcrab import ssh

def pytest_addoption(parser):
    parser.addoption(
        "--no-playback",
        dest="playback",
        action="store_false",
        default=True,
        help="If set, will disable payback from any past recorded session and instead record a new one",)
 
@pytest.fixture(scope="function")
def vcr(monkeypatch, request):
    vcr, cassette = setup_vcr(monkeypatch, request)
    yield vcr
    teardown_vcr(vcr, cassette)

@pytest.fixture(scope="function")
def tmphomedir(tmpdir, monkeypatch, vcr):
    tmpdir.join("config").mkdir()
    monkeypatch.setattr(config, "get_home_config_dir", lambda: str(tmpdir.join("config")))

    if vcr.is_playback():
        tmpdir.join("ssh").mkdir()
        tmpdir.join("ssh").join("id_rsa.pub").write("ssh-rsa boguskey\n")
        monkeypatch.setattr(ssh, "get_ssh_dir", lambda: str(tmpdir.join("ssh")))
    
