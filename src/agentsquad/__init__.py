# Copyright 2026 agentsquad contributors
# Licensed under the Apache License, Version 2.0

"""agentsquad - multi-agent message broker."""

from importlib.metadata import PackageNotFoundError, version as _version

try:
    __version__ = _version("agentsquad")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"
