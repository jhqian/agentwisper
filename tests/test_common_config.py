import os
from agentwisper.common.config import BrokerConfig, load_config


def test_default_config():
    config = BrokerConfig()
    assert config.db_path == "agentwisper.db"
    assert config.rpc_timeout == 30
    assert config.message_poll_limit == 50
    assert config.retention_days == 30
    assert config.http_host == "127.0.0.1"
    assert config.disconnected_ttl_days == 7
    assert config.cleanup_interval_minutes == 60
    assert config.message_buffer_limit == 100


def test_config_from_env():
    os.environ["AGENTWHISPER_DB_PATH"] = "/tmp/test.db"
    os.environ["AGENTWHISPER_RPC_TIMEOUT"] = "60"
    os.environ["AGENTWHISPER_HTTP_HOST"] = "0.0.0.0"
    try:
        config = load_config()
        assert config.db_path == "/tmp/test.db"
        assert config.rpc_timeout == 60
        assert config.http_host == "0.0.0.0"
    finally:
        del os.environ["AGENTWHISPER_DB_PATH"]
        del os.environ["AGENTWHISPER_RPC_TIMEOUT"]
        del os.environ["AGENTWHISPER_HTTP_HOST"]


def test_config_defaults_when_env_not_set():
    config = load_config()
    assert config == BrokerConfig()


def test_config_ttl_from_env():
    os.environ["AGENTWHISPER_DISCONNECTED_TTL_DAYS"] = "14"
    os.environ["AGENTWHISPER_CLEANUP_INTERVAL_MINUTES"] = "30"
    try:
        config = load_config()
        assert config.disconnected_ttl_days == 14
        assert config.cleanup_interval_minutes == 30
    finally:
        del os.environ["AGENTWHISPER_DISCONNECTED_TTL_DAYS"]
        del os.environ["AGENTWHISPER_CLEANUP_INTERVAL_MINUTES"]
