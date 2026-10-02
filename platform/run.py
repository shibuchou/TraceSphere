#!/usr/bin/env python3
"""TraceSphere platform service (member B) entry point.

Usage::

    python run.py --config config/platform.json
    python run.py --provider fixture --fixtures fixtures --host 0.0.0.0 --port 8000
    ZSVIRT_PROVIDER=rest ZSVIRT_PASSWORD=... python run.py
"""

import argparse
import logging
import os
import sys
import threading
import time

from tsplatform import __version__
from tsplatform.api import serve
from tsplatform.app import PlatformApp
from tsplatform.config import load_config

logger = logging.getLogger("tsplatform.run")


def _parse_args(argv):
    parser = argparse.ArgumentParser(description="TraceSphere platform service")
    parser.add_argument("--config", "-c", help="path to JSON config (default: config/platform.json if present)")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--db")
    parser.add_argument("--provider", choices=("rest", "fixture"))
    parser.add_argument("--fixtures")
    parser.add_argument("--scenario")
    parser.add_argument("--base-url")
    parser.add_argument("--log-level")
    parser.add_argument("--no-sync", action="store_true", help="skip the startup ZSvirt sync")
    parser.add_argument("--version", action="version", version="TraceSphere platform %s" % __version__)
    return parser.parse_args(argv)


def _apply_overrides(cfg, args):
    platform = cfg.setdefault("platform", {})
    zsvirt = cfg.setdefault("zsvirt", {})
    if args.host:
        platform["host"] = args.host
    if args.port:
        platform["port"] = args.port
    if args.db:
        platform["db_path"] = args.db
    if args.provider:
        zsvirt["provider"] = args.provider
    if args.fixtures:
        zsvirt["fixtures_dir"] = args.fixtures
    if args.scenario:
        zsvirt["fixture_scenario"] = args.scenario
    if args.base_url:
        zsvirt["base_url"] = args.base_url
    if args.log_level:
        platform["log_level"] = args.log_level
    base_dir = platform.get("base_dir") or os.getcwd()
    for key, section in (("db_path", "platform"), ("fixtures_dir", "zsvirt")):
        value = cfg[section].get(key)
        if value and not os.path.isabs(value):
            cfg[section][key] = os.path.normpath(os.path.join(base_dir, value))
    return cfg


def main(argv=None):
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    config_path = args.config
    if not config_path:
        candidate = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "platform.json")
        config_path = candidate if os.path.isfile(candidate) else None
    cfg = load_config(config_path)
    cfg = _apply_overrides(cfg, args)

    level = str((cfg.get("platform") or {}).get("log_level") or "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    # 安全基线：非回环绑定必须配置 API token（显式 TRACESPHERE_ALLOW_INSECURE=1 才放行）
    bind_host = str(cfg["platform"].get("host") or "127.0.0.1")
    api_token = str(((cfg.get("api") or {}).get("token")) or "").strip()
    if bind_host not in ("127.0.0.1", "localhost", "::1") and not api_token:
        if os.environ.get("TRACESPHERE_ALLOW_INSECURE") != "1":
            logger.error(
                "拒绝启动：host=%s 为非回环绑定但未配置 TRACESPHERE_API_TOKEN。"
                "请设置 token（推荐），或显式 TRACESPHERE_ALLOW_INSECURE=1 允许不安全模式。",
                bind_host,
            )
            return 3
        logger.warning("以无 token 的不安全模式监听 %s（TRACESPHERE_ALLOW_INSECURE=1）", bind_host)

    try:
        app = PlatformApp(cfg)
    except RuntimeError as exc:
        logger.error("cannot start platform: %s", exc)
        return 2

    if cfg["zsvirt"].get("sync_on_start", True) and not args.no_sync:
        try:
            result = app.sync(ingest_events=True)
            logger.info(
                "startup sync provider=%s/%s ok=%s resources=%d edges=%d events=%d errors=%s",
                result.provider,
                result.mode,
                result.ok,
                result.resources,
                result.edges,
                result.events_ingested,
                result.errors or "-",
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("startup sync failed (service still starting): %s", exc)

    # 周期性 ZSvirt 资源/告警同步（方案 §5：可配置周期同步；0 = 仅启动同步）
    interval = float(cfg["zsvirt"].get("sync_interval_sec") or 0)
    if interval > 0:

        def _sync_loop():
            while True:
                time.sleep(interval)
                try:
                    result = app.sync(ingest_events=True)
                    logger.info(
                        "periodic sync ok=%s resources=%d edges=%d events=%d errors=%s",
                        result.ok,
                        result.resources,
                        result.edges,
                        result.events_ingested,
                        result.errors or "-",
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error("periodic sync failed: %s", exc)

        threading.Thread(target=_sync_loop, daemon=True, name="zsvirt-sync").start()
        logger.info("periodic ZSvirt sync enabled: every %.0fs", interval)

    server = serve(app, cfg["platform"]["host"], cfg["platform"]["port"])
    logger.info("ready: http://%s:%s/api/v1/health", cfg["platform"]["host"], cfg["platform"]["port"])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("shutting down")
    finally:
        server.server_close()
        app.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
