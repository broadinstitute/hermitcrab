import importlib.metadata

try:
    __version__ = importlib.metadata.version("hermit")
except importlib.metadata.PackageNotFoundError:
    __version__ = "unknown"
