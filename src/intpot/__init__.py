"""intpot - Universal converter between CLI, MCP, and API interfaces."""

from importlib.metadata import PackageNotFoundError, version

from intpot.converter import IntpotApp, inspect_app, load
from intpot.runtime import App

try:
    __version__ = version("intpot")
except PackageNotFoundError:  # source tree that was never installed
    __version__ = "0.0.0+unknown"

__all__ = ["App", "IntpotApp", "inspect_app", "load"]
