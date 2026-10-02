"""RESTProvider: ZSvirt native REST API (方案 §4.1/§4.2).

Auth flow (handoff §2.3):

- ``PUT {base}/accounts/login`` with ``{"logInByAccount": {"accountName": ..., "password": <sha512 hex>}}``
- subsequent requests carry ``Authorization: OAuth <session-uuid>``

The password is never logged, never stored in the database, and not kept in
plain text longer than necessary (方案 §8).
"""

import json
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from ..util import sha512_hex
from .base import Snapshot, ZSvirtProvider
from .mapper import COLLECTIONS, snapshot_from_raw

DEFAULT_PATHS = {
    "zones": "zones",
    "clusters": "clusters",
    "hosts": "hosts",
    "vms": "vm-instances",
    "images": "images",
    "l3_networks": "l3-networks",
    "l2_networks": "l2-networks",
    "port_groups": "port-groups",
    "primary_storages": "primary-storages",
    "backup_storages": "backup-storages",
    "instance_offerings": "instance-offerings",
    "alarms": "zwatch/alarms",
    "events": "zwatch/events",
}

_AUTH_HINTS = ("SESSION", "AUTH", "TOKEN")


class ZSvirtError(RuntimeError):
    def __init__(self, message: str, path: Optional[str] = None, status: Optional[int] = None, code: Optional[str] = None):
        super().__init__(message)
        self.path = path
        self.status = status
        self.code = code

    def to_dict(self) -> Dict[str, Any]:
        return {"message": str(self), "path": self.path, "status": self.status, "code": self.code}


class ZSvirtRestClient(object):
    def __init__(
        self,
        base_url: str,
        account: str,
        password: str,
        timeout: float = 20.0,
        verify_tls: bool = False,
        page_size: int = 100,
        paths: Optional[Dict[str, str]] = None,
    ):
        if not base_url:
            raise ValueError("ZSvirt base_url is required")
        self.base_url = base_url.rstrip("/")
        self.account = account
        self._password = password or ""
        self.timeout = float(timeout or 20.0)
        self.verify_tls = bool(verify_tls)
        self.page_size = max(1, int(page_size or 100))
        self.paths = dict(DEFAULT_PATHS)
        if paths:
            self.paths.update({k: v for k, v in paths.items() if v})
        self._session_uuid: Optional[str] = None
        if self.base_url.startswith("https") and not self.verify_tls:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            self._ssl_context = context
        else:
            self._ssl_context = None

    # ----- auth ----------------------------------------------------------
    @property
    def session_uuid(self) -> Optional[str]:
        return self._session_uuid

    def login(self) -> str:
        body = {
            "logInByAccount": {
                "accountName": self.account,
                "password": sha512_hex(self._password),
            }
        }
        payload = self._request("PUT", "accounts/login", body=body, retry_auth=False)
        session = None
        if isinstance(payload, dict):
            inventory = payload.get("inventory")
            if isinstance(inventory, dict):
                session = inventory.get("uuid") or inventory.get("sessionId")
            if not session:
                session = payload.get("sessionId")
        if not session:
            raise ZSvirtError("login response did not contain a session uuid", path="accounts/login")
        self._session_uuid = str(session)
        return self._session_uuid

    def ensure_login(self) -> None:
        if not self._session_uuid:
            self.login()

    # ----- transport ------------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        retry_auth: bool = True,
    ) -> Dict[str, Any]:
        url = "%s/%s" % (self.base_url, path.lstrip("/"))
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._session_uuid:
            headers["Authorization"] = "OAuth %s" % self._session_uuid
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            response = urllib.request.urlopen(request, timeout=self.timeout, context=self._ssl_context)
            raw = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            payload = _parse_json(raw)
            status = exc.code
            if retry_auth and status in (401, 403) and path != "accounts/login":
                self._session_uuid = None
                self.login()
                return self._request(method, path, body=body, params=params, retry_auth=False)
            raise ZSvirtError(
                _error_message(payload) or ("HTTP %s" % status),
                path=path,
                status=status,
                code=_error_code(payload),
            )
        except urllib.error.URLError as exc:
            raise ZSvirtError("connection failed: %s" % exc.reason, path=path)
        except (socket.timeout, TimeoutError):
            raise ZSvirtError("request timed out after %ss" % self.timeout, path=path)

        payload = _parse_json(raw)
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            code = _error_code(payload)
            message = _error_message(payload) or "ZSvirt API error"
            if retry_auth and path != "accounts/login" and _looks_like_auth_error(code):
                self._session_uuid = None
                self.login()
                return self._request(method, path, body=body, params=params, retry_auth=False)
            raise ZSvirtError(message, path=path, code=code)
        return payload

    def query(self, path: str, params: Optional[Dict[str, Any]] = None, page_size: Optional[int] = None) -> Dict[str, Any]:
        """Paginated query aggregating ``inventories`` across pages."""
        size = max(1, int(page_size or self.page_size))
        collected: List[Dict[str, Any]] = []
        total: Optional[int] = None
        start = 0
        for _ in range(500):
            page_params = dict(params or {})
            page_params.setdefault("limit", size)
            page_params["start"] = start
            page = self._request("GET", path, params=page_params)
            if not isinstance(page, dict) or "inventories" not in page:
                return page
            items = page.get("inventories") or []
            collected.extend(item for item in items if isinstance(item, dict))
            total = page.get("total")
            if not items or len(items) < size:
                break
            if total is not None and len(collected) >= int(total):
                break
            start += len(items)
        return {
            "inventories": collected,
            "total": int(total) if total is not None else len(collected),
        }

    # ----- convenience queries -------------------------------------------
    def query_collection(self, logical_name: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        path = self.paths.get(logical_name)
        if not path:
            raise ZSvirtError("no configured path for collection %s" % logical_name)
        return self.query(path, params=params)

    def query_by_uuid(self, logical_name: str, uuid: str) -> Dict[str, Any]:
        return self.query_collection(logical_name, {"q": "uuid=%s" % uuid})

    def query_vms(self) -> Dict[str, Any]:
        return self.query_collection("vms")

    def query_hosts(self) -> Dict[str, Any]:
        return self.query_collection("hosts")


class RESTProvider(ZSvirtProvider):
    name = "rest"
    mode = "real"

    def __init__(self, client: ZSvirtRestClient, include: Optional[List[str]] = None):
        self.client = client
        self.include = include or list(COLLECTIONS) + ["alarms", "events"]

    def snapshot(self) -> Snapshot:
        self.client.ensure_login()
        raw: Dict[str, Any] = {}
        errors: Dict[str, str] = {}
        for logical in self.include:
            if logical not in self.client.paths:
                continue
            try:
                raw[logical] = self.client.query_collection(logical)
            except ZSvirtError as exc:
                errors[logical] = str(exc)
                raw[logical] = None
        snapshot = snapshot_from_raw(raw, mode=self.mode, provider=self.name)
        snapshot.errors.update(errors)
        return snapshot

    @property
    def description(self) -> str:
        return "rest (%s)" % self.client.base_url


def _parse_json(raw: str) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except ValueError:
        return {"raw": raw[:2000]}


def _error_code(payload: Any) -> Optional[str]:
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        code = payload["error"].get("code")
        return str(code) if code is not None else None
    return None


def _error_message(payload: Any) -> Optional[str]:
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        error = payload["error"]
        for key in ("description", "details", "message"):
            if error.get(key):
                return str(error[key])
    return None


def _looks_like_auth_error(code: Optional[str]) -> bool:
    if not code:
        return False
    upper = code.upper()
    return any(hint in upper for hint in _AUTH_HINTS)
