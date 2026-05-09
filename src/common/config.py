# Copyright 2026 vibe-agentsquad contributors
# Licensed under the Apache License, Version 2.0

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class BrokerConfig:
    db_path: str = "agentsquad.db"
    heartbeat_interval: int = 30
    heartbeat_timeout: int = 90
    rpc_timeout: int = 30
    message_poll_limit: int = 50
    retention_days: int = 30
    default_transport: str = "stdio"
    http_port: int = 8000


def load_config() -> BrokerConfig:
    return BrokerConfig(
        db_path=os.environ.get("AGENTSQUAD_DB_PATH", BrokerConfig.db_path),
        heartbeat_interval=int(os.environ.get("AGENTSQUAD_HEARTBEAT_INTERVAL", "30")),
        heartbeat_timeout=int(os.environ.get("AGENTSQUAD_HEARTBEAT_TIMEOUT", "90")),
        rpc_timeout=int(os.environ.get("AGENTSQUAD_RPC_TIMEOUT", "30")),
        message_poll_limit=int(os.environ.get("AGENTSQUAD_POLL_LIMIT", "50")),
        retention_days=int(os.environ.get("AGENTSQUAD_RETENTION_DAYS", "30")),
        default_transport=os.environ.get("AGENTSQUAD_TRANSPORT", "stdio"),
        http_port=int(os.environ.get("AGENTSQUAD_HTTP_PORT", "8000")),
    )
