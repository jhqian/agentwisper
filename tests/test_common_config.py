import os
from common.config import BrokerConfig, load_config


def test_default_config():
    config = BrokerConfig()
    assert config.db_path == "agentsquad.db"
    assert config.heartbeat_interval == 30
    assert config.heartbeat_timeout == 90
    assert config.rpc_timeout == 30
    assert config.message_poll_limit == 50
    assert config.retention_days == 30


def test_config_from_env():
    os.environ["AGENTSQUAD_DB_PATH"] = "/tmp/test.db"
    os.environ["AGENTSQUAD_RPC_TIMEOUT"] = "60"
    try:
        config = load_config()
        assert config.db_path == "/tmp/test.db"
        assert config.rpc_timeout == 60
    finally:
        del os.environ["AGENTSQUAD_DB_PATH"]
        del os.environ["AGENTSQUAD_RPC_TIMEOUT"]


def test_config_defaults_when_env_not_set():
    config = load_config()
    assert config == BrokerConfig()
