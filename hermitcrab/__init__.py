import importlib.metadata

try:
    __version__ = importlib.metadata.version("hermitcrab")
except importlib.metadata.PackageNotFoundError:
    __version__ = "unknown"
