import pytest
from .hermitcrab.gcloud_vcr import setup_vcr, teardown_vcr;
from hermitcrab import config

def pytest_addoption(parser):
    parser.addoption(
        "--no-playback",
        dest="playback",
        action="store_false",
        default=True,
        help="If set, will disable payback from any past recorded session and instead record a new one",)
 
@pytest.fixture(scope="function")
def vcr(monkeypatch, tmpdir, request):
    state = setup_vcr(monkeypatch, request)
    yield
    teardown_vcr(*state)

@pytest.fixture(scope="function")
def tmphomedir(tmpdir, monkeypatch):
    tmpdir.join("config").mkdir()
    monkeypatch.setattr(config, "get_home_config_dir", lambda: str(tmpdir.join("config")))
