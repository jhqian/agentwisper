# Copyright 2026 agentwisper contributors
# Licensed under the Apache License, Version 2.0

"""agentwisper - multi-agent message broker."""

from importlib.metadata import PackageNotFoundError, version as _version

try:
    __version__ = _version("agentwisper")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"
