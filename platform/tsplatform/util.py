"""Small shared helpers (stdlib only, Python 3.8 compatible)."""

import datetime
import hashlib
import json
import re
import uuid
from typing import Any, Dict, Optional

UTC = datetime.timezone.utc

_ZSTACK_DATE_FORMATS = (
    "%b %d, %Y %H:%M:%S",
    "%b %d, %Y %I:%M:%S %p",
    "%b  %d, %Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
)


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(tz=UTC)


def format_rfc3339(dt: Optional[datetime.datetime] = None) -> str:
    """Return UTC RFC3339 with millisecond precision, e.g. 2026-09-20T08:00:00.123Z."""
    if dt is None:
        dt = now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    dt = dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + "%03d" % (dt.microsecond // 1000) + "Z"


def parse_timestamp(value: Any, default: Optional[datetime.datetime] = None) -> Optional[datetime.datetime]:
    """Parse RFC3339 / ``YYYY-MM-DD HH:MM:SS`` / ZStack display dates into aware UTC.

    Returns ``default`` (may be None) when the value cannot be parsed.
    """
    if value is None:
        return default
    if isinstance(value, datetime.datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    if isinstance(value, (int, float)):
        # epoch seconds (or milliseconds)
        ts = float(value)
        if ts > 1e12:
            ts = ts / 1000.0
        return datetime.datetime.fromtimestamp(ts, tz=UTC)
    text = str(value).strip()
    if not text:
        return default
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except ValueError:
        pass
    collapsed = re.sub(r"\s+", " ", text)
    for fmt in _ZSTACK_DATE_FORMATS:
        try:
            dt = datetime.datetime.strptime(collapsed, fmt)
            return dt.replace(tzinfo=UTC)
        except ValueError:
            continue
    return default


def rfc3339_or_none(value: Any) -> Optional[str]:
    dt = parse_timestamp(value)
    return format_rfc3339(dt) if dt else None


def sha512_hex(text: str) -> str:
    return hashlib.sha512(text.encode("utf-8")).hexdigest()


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def new_id(prefix: str) -> str:
    return "%s-%s" % (prefix, uuid.uuid4().hex[:16])


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def json_loads(text: Any, default: Any = None) -> Any:
    if text is None:
        return default
    if isinstance(text, (dict, list)):
        return text
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def merge_dicts(base: Optional[Dict[str, Any]], extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Shallow-merge two dicts, ``extra`` wins. Never mutates inputs."""
    merged: Dict[str, Any] = {}
    if isinstance(base, dict):
        merged.update(base)
    if isinstance(extra, dict):
        merged.update(extra)
    return merged


def truncate(text: Any, limit: int = 500) -> str:
    s = "" if text is None else str(text)
    return s if len(s) <= limit else s[: limit - 3] + "..."


def safe_severity(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip().lower()
    mapping = {
        "emergency": "critical",
        "emergent": "critical",
        "important": "major",
        "normal": "info",
        "critical": "critical",
        "error": "major",
        "major": "major",
        "alert": "major",
        "warning": "warning",
        "minor": "warning",
        "warn": "warning",
        "notice": "info",
        "info": "info",
        "informational": "info",
        "debug": "info",
    }
    return mapping.get(s, s if s in ("critical", "major", "warning", "info") else None)
