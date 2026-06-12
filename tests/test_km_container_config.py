import pytest
import os
import docker
from unittest.mock import patch
from main import KernelManager

def test_get_container_config_defaults():
    """Verify default configuration when no environment variables are set."""
    km = KernelManager()
    # Ensure environment is clean for this test
    with patch.dict(os.environ, {}, clear=True):
        config = km._get_container_config()

    assert config["mem_limit"] == "512m"
    assert config["nano_cpus"] == 500000000
    assert config["network_disabled"] is True
    assert config["device_requests"] == []

def test_get_container_config_custom_limits():
    """Verify custom memory and CPU limits."""
    km = KernelManager()
    custom_env = {
        "RCE_MEM_LIMIT": "1g",
        "RCE_CPU_LIMIT": "1000000000"
    }
    with patch.dict(os.environ, custom_env):
        config = km._get_container_config()

    assert config["mem_limit"] == "1g"
    assert config["nano_cpus"] == 1000000000

def test_get_container_config_network_enabled():
    """Verify network configuration when enabled."""
    km = KernelManager()

    # Test True
    with patch.dict(os.environ, {"RCE_NETWORK_ENABLED": "true"}):
        config = km._get_container_config()
        assert config["network_disabled"] is False

    # Test TRUE (case-insensitive)
    with patch.dict(os.environ, {"RCE_NETWORK_ENABLED": "TRUE"}):
        config = km._get_container_config()
        assert config["network_disabled"] is False

    # Test false
    with patch.dict(os.environ, {"RCE_NETWORK_ENABLED": "false"}):
        config = km._get_container_config()
        assert config["network_disabled"] is True

def test_get_container_config_gpu_enabled():
    """Verify GPU configuration when enabled."""
    km = KernelManager()

    with patch.dict(os.environ, {"RCE_GPU_ENABLED": "true"}):
        config = km._get_container_config()
        assert len(config["device_requests"]) == 1
        req = config["device_requests"][0]
        assert isinstance(req, docker.types.DeviceRequest)
        assert req["Count"] == -1
        assert req["Capabilities"] == [['gpu']]

def test_get_container_config_gpu_disabled():
    """Verify GPU configuration when disabled."""
    km = KernelManager()

    with patch.dict(os.environ, {"RCE_GPU_ENABLED": "false"}):
        config = km._get_container_config()
        assert config["device_requests"] == []
