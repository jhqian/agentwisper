# Copyright 2026 agentsquad contributors
# Licensed under the Apache License, Version 2.0

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class BrokerConfig:
    db_path: str = "agentsquad.db"
    rpc_timeout: int = 30
    message_poll_limit: int = 50
    retention_days: int = 30
    http_port: int = 8000
    http_host: str = "127.0.0.1"
    disconnected_ttl_days: int = 7
    cleanup_interval_minutes: int = 60
    liveness_interval: int = 30
    liveness_timeout: int = 90


def load_config() -> BrokerConfig:
    return BrokerConfig(
        db_path=os.environ.get("AGENTSQUAD_DB_PATH", BrokerConfig.db_path),
        rpc_timeout=int(os.environ.get("AGENTSQUAD_RPC_TIMEOUT", "30")),
        message_poll_limit=int(os.environ.get("AGENTSQUAD_POLL_LIMIT", "50")),
        retention_days=int(os.environ.get("AGENTSQUAD_RETENTION_DAYS", "30")),
        http_port=int(os.environ.get("AGENTSQUAD_HTTP_PORT", "8000")),
        http_host=os.environ.get("AGENTSQUAD_HTTP_HOST", BrokerConfig.http_host),
        disconnected_ttl_days=int(os.environ.get("AGENTSQUAD_DISCONNECTED_TTL_DAYS", "7")),
        cleanup_interval_minutes=int(os.environ.get("AGENTSQUAD_CLEANUP_INTERVAL_MINUTES", "60")),
        liveness_interval=int(os.environ.get("AGENTSQUAD_LIVENESS_INTERVAL", "30")),
        liveness_timeout=int(os.environ.get("AGENTSQUAD_LIVENESS_TIMEOUT", "90")),
    )
