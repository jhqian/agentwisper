# Copyright 2026 vibe-agentsquad contributors
# Licensed under the Apache License, Version 2.0

"""Shared pytest fixtures for vibe-agentsquad tests."""

import pytest
from persistence.database import AsyncDatabase


@pytest.fixture
async def db(tmp_path):
    database = AsyncDatabase(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()
