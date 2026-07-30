# Copyright 2026 agentwisper contributors
# Licensed under the Apache License, Version 2.0

"""Shared pytest fixtures for agentwisper tests."""

import pytest
from agentwisper.persistence.database import AsyncDatabase


@pytest.fixture
async def db(tmp_path):
    database = AsyncDatabase(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()
