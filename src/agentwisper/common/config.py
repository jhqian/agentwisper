# Copyright 2026 agentwisper contributors
# Licensed under the Apache License, Version 2.0

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class BrokerConfig:
    db_path: str = "agentwisper.db"
    rpc_timeout: int = 30
    message_poll_limit: int = 50
    retention_days: int = 30
    http_port: int = 8000
    http_host: str = "127.0.0.1"
    disconnected_ttl_days: int = 7
    cleanup_interval_minutes: int = 60
    message_buffer_limit: int = 100


def load_config() -> BrokerConfig:
    return BrokerConfig(
        db_path=os.environ.get("AGENTWHISPER_DB_PATH", BrokerConfig.db_path),
        rpc_timeout=int(os.environ.get("AGENTWHISPER_RPC_TIMEOUT", "30")),
        message_poll_limit=int(os.environ.get("AGENTWHISPER_POLL_LIMIT", "50")),
        retention_days=int(os.environ.get("AGENTWHISPER_RETENTION_DAYS", "30")),
        http_port=int(os.environ.get("AGENTWHISPER_HTTP_PORT", "8000")),
        http_host=os.environ.get("AGENTWHISPER_HTTP_HOST", BrokerConfig.http_host),
        disconnected_ttl_days=int(os.environ.get("AGENTWHISPER_DISCONNECTED_TTL_DAYS", "7")),
        cleanup_interval_minutes=int(os.environ.get("AGENTWHISPER_CLEANUP_INTERVAL_MINUTES", "60")),
        message_buffer_limit=int(os.environ.get("AGENTWHISPER_MESSAGE_BUFFER_LIMIT", "100")),
    )
