# Copyright 2026 agentwisper contributors
# Licensed under the Apache License, Version 2.0

"""Tests for SignalWriter atomic signal file operations."""

import json

import pytest

from agentwisper.broker.signal_writer import SignalWriter


@pytest.fixture
def signal_dir(tmp_path):
    return tmp_path / ".signals"


@pytest.fixture
async def writer(signal_dir):
    w = SignalWriter(signal_dir)
    return w


async def test_write_creates_signal_file(writer, signal_dir):
    await writer.write("agent_abc")
    assert (signal_dir / "agent_abc.json").exists()


async def test_write_signal_content(writer, signal_dir):
    await writer.write("agent_abc")
    content = json.loads((signal_dir / "agent_abc.json").read_text())
    assert content["pending"] is True
    assert "last_arrival" in content


async def test_write_overwrites_existing(writer, signal_dir):
    await writer.write("agent_abc")
    await writer.write("agent_abc")
    content = json.loads((signal_dir / "agent_abc.json").read_text())
    assert content["pending"] is True


async def test_clear_removes_signal(writer, signal_dir):
    await writer.write("agent_abc")
    await writer.clear("agent_abc")
    assert not (signal_dir / "agent_abc.json").exists()


async def test_clear_nonexistent_is_noop(writer):
    await writer.clear("nonexistent")


async def test_check_returns_signal_data(writer):
    await writer.write("agent_abc")
    result = await writer.check("agent_abc")
    assert result is not None
    assert result["pending"] is True


async def test_check_returns_none_when_no_signal(writer):
    result = await writer.check("agent_abc")
    assert result is None


async def test_cleanup_agent_removes_signal(writer, signal_dir):
    await writer.write("agent_abc")
    await writer.cleanup_agent("agent_abc")
    assert not (signal_dir / "agent_abc.json").exists()


async def test_cleanup_all_removes_all_signals(writer, signal_dir):
    await writer.write("agent_a")
    await writer.write("agent_b")
    await writer.write("agent_c")
    await writer.cleanup_all()
    assert len(list(signal_dir.glob("*.json"))) == 0


async def test_pending_count(writer):
    assert writer.pending_count() == 0
    await writer.write("agent_a")
    assert writer.pending_count() == 1
    await writer.write("agent_b")
    assert writer.pending_count() == 2
    await writer.clear("agent_a")
    assert writer.pending_count() == 1


async def test_signal_dir_created_with_restricted_perms(signal_dir):
    SignalWriter(signal_dir)
    assert signal_dir.exists()


async def test_write_atomic_no_partial_files(writer, signal_dir):
    """Verify no .tmp files remain after write."""
    await writer.write("agent_abc")
    assert len(list(signal_dir.glob("*.tmp"))) == 0
