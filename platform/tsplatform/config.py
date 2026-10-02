"""Configuration loading (JSON) with environment overrides.

Relative paths are resolved against the platform root (the directory that
contains ``run.py``), so the service can be started from anywhere.
"""

import copy
import json
import os
from typing import Any, Dict

PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULTS: Dict[str, Any] = {
    "platform": {
        "host": "127.0.0.1",
        "port": 8000,
        "db_path": "data/tracesphere.db",
        "log_level": "INFO",
    },
    "zsvirt": {
        "provider": "fixture",
        "base_url": "http://127.0.0.1:8080/zstack/v1",
        "account": "admin",
        "password": None,
        "password_env": "ZSVIRT_PASSWORD",
        "fixtures_dir": "fixtures",
        "fixture_scenario": None,
        "sync_on_start": True,
        "sync_interval_sec": 0,
        "request_timeout_sec": 20,
        "verify_tls": False,
        "page_size": 100,
        # Query paths; override when a ZSvirt build exposes different paths.
        "paths": {
            "hosts": "hosts",
            "vms": "vm-instances",
            "zones": "zones",
            "clusters": "clusters",
            "images": "images",
            "l3_networks": "l3-networks",
            "l2_networks": "l2-networks",
            # verified on real ZSvirt 2026-09-20: port groups live under this path
            "port_groups": "l2-networks/port-groups",
            # verified on real ZSvirt 2026-09-20: singular paths
            "primary_storages": "primary-storage",
            "backup_storages": "backup-storage",
            "instance_offerings": "instance-offerings",
            # W1: verify on real ZSvirt and override in config if paths differ
            "alarms": "zwatch/alarms",
            "events": "zwatch/events",
        },
    },
    "api": {
        "token": "",
        "cors_origins": ["*"],
        "max_body_bytes": 5 * 1024 * 1024,
        # 写接口最小限流（每客户端 IP 每分钟的 POST 次数；0 = 关闭）
        "rate_limit_per_min": 600,
    },
    "correlation": {
        "window_seconds": 5.0,
        "max_events": 5000,
    },
    # 无 GPU 硬件的降级模式（赛题 §4）：注册模拟 GPU 资源 + Host/Gpu/VM 边，
    # 由 workload/mock/gpu_exporter.py 上报模拟 DCGM 指标。默认关闭。
    "mock_gpu": {
        "enabled": False,
        "uuid": "mock-gpu0",
        "name": "Mock GPU 0 (DCGM)",
        "vendor": "NVIDIA (Mock)",
        "memory_total_bytes": 8589934592,
        "vm_uuid": "",
        "host_uuid": "",
    },
}

_ENV_MAP = (
    ("TRACESPHERE_HOST", ("platform", "host")),
    ("TRACESPHERE_PORT", ("platform", "port")),
    ("TRACESPHERE_DB", ("platform", "db_path")),
    ("TRACESPHERE_LOG_LEVEL", ("platform", "log_level")),
    ("ZSVIRT_PROVIDER", ("zsvirt", "provider")),
    ("ZSVIRT_BASE_URL", ("zsvirt", "base_url")),
    ("ZSVIRT_ACCOUNT", ("zsvirt", "account")),
    ("ZSVIRT_PASSWORD", ("zsvirt", "password")),
    ("ZSVIRT_FIXTURES", ("zsvirt", "fixtures_dir")),
    ("ZSVIRT_SCENARIO", ("zsvirt", "fixture_scenario")),
    ("ZSVIRT_SYNC_INTERVAL", ("zsvirt", "sync_interval_sec")),
    ("TRACESPHERE_API_TOKEN", ("api", "token")),
    ("TRACESPHERE_RATE_LIMIT", ("api", "rate_limit_per_min")),
    ("TRACESPHERE_MOCK_GPU", ("mock_gpu", "enabled")),
    ("TRACESPHERE_MOCK_GPU_UUID", ("mock_gpu", "uuid")),
    ("TRACESPHERE_MOCK_GPU_VM", ("mock_gpu", "vm_uuid")),
)


def _deep_merge(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _set_path(cfg: Dict[str, Any], path: tuple, value: Any) -> None:
    node = cfg
    for key in path[:-1]:
        node = node.setdefault(key, {})
    if path[-1] == "enabled":
        node[path[-1]] = str(value).strip().lower() in ("1", "true", "yes", "on")
        return
    if path[-1] == "port" or path[-1].endswith("_sec") or path[-1].endswith("size") or path[-1].endswith("_per_min"):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return
    node[path[-1]] = value


def load_config(path: str = None) -> Dict[str, Any]:
    """Load config from JSON file (optional) and apply env overrides."""
    path = path or os.environ.get("TRACESPHERE_CONFIG")
    cfg = copy.deepcopy(DEFAULTS)
    if path:
        with open(path, "r", encoding="utf-8") as handle:
            file_cfg = json.load(handle)
        cfg = _deep_merge(cfg, file_cfg)
    for env_name, target in _ENV_MAP:
        value = os.environ.get(env_name)
        if value is not None and value != "":
            _set_path(cfg, target, value)
    cfg["platform"]["base_dir"] = PLATFORM_ROOT
    for key in ("db_path", "fixtures_dir"):
        section = "platform" if key == "db_path" else "zsvirt"
        value = cfg[section][key]
        if value and not os.path.isabs(value):
            cfg[section][key] = os.path.normpath(os.path.join(PLATFORM_ROOT, value))
    return cfg


def resolve_zsvirt_password(cfg: Dict[str, Any]) -> str:
    """Resolve the ZSvirt password from config/env. Never log the result."""
    zsvirt = cfg.get("zsvirt", {})
    if zsvirt.get("password"):
        return zsvirt["password"]
    env_name = zsvirt.get("password_env") or "ZSVIRT_PASSWORD"
    return os.environ.get(env_name, "")
