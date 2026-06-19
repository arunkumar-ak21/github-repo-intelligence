"""Small signed-cookie session middleware.

This avoids adding a hard dependency on Starlette's optional session backend
while still giving the app real browser sessions for GitHub login.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from http.cookies import SimpleCookie
from typing import Any

from starlette.datastructures import Headers, MutableHeaders


def _b64_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64_decode(value: str) -> bytes:
    padded = value + ("=" * (-len(value) % 4))
    return base64.urlsafe_b64decode(padded.encode("ascii"))


class SignedCookieSessionMiddleware:
    """Attach a signed, JSON-backed session dictionary to request.session."""

    def __init__(
        self,
        app,
        *,
        secret_key: str,
        cookie_name: str,
        max_age: int,
        https_only: bool = False,
        same_site: str = "lax",
    ) -> None:
        self.app = app
        self.secret_key = secret_key.encode("utf-8")
        self.cookie_name = cookie_name
        self.max_age = max_age
        self.https_only = https_only
        self.same_site = same_site

    def _sign(self, payload: str) -> str:
        return hmac.new(self.secret_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()

    def _load_session(self, cookie_value: str | None) -> dict[str, Any]:
        if not cookie_value or "." not in cookie_value:
            return {}
        payload, signature = cookie_value.rsplit(".", 1)
        expected = self._sign(payload)
        if not hmac.compare_digest(signature, expected):
            return {}
        try:
            data = json.loads(_b64_decode(payload).decode("utf-8"))
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        expires_at = data.get("_expires_at")
        if expires_at and float(expires_at) < time.time():
            return {}
        return {key: value for key, value in data.items() if key != "_expires_at"}

    def _dump_session(self, session: dict[str, Any]) -> str:
        payload = dict(session)
        payload["_expires_at"] = int(time.time()) + self.max_age
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        encoded = _b64_encode(raw)
        return f"{encoded}.{self._sign(encoded)}"

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        cookie_header = headers.get("cookie", "")
        cookies = SimpleCookie(cookie_header)
        had_cookie = self.cookie_name in cookies
        cookie_value = cookies[self.cookie_name].value if had_cookie else None
        scope["session"] = self._load_session(cookie_value)

        async def send_wrapper(message):
            if message["type"] == "http.response.start" and scope["type"] == "http":
                mutable = MutableHeaders(scope=message)
                session = scope.get("session") or {}
                if session:
                    value = self._dump_session(session)
                    parts = [
                        f"{self.cookie_name}={value}",
                        f"Max-Age={self.max_age}",
                        "Path=/",
                        "HttpOnly",
                        f"SameSite={self.same_site}",
                    ]
                    if self.https_only:
                        parts.append("Secure")
                    mutable.append("Set-Cookie", "; ".join(parts))
                elif had_cookie:
                    mutable.append(
                        "Set-Cookie",
                        f"{self.cookie_name}=; Max-Age=0; Path=/; HttpOnly; SameSite={self.same_site}",
                    )
            await send(message)

        await self.app(scope, receive, send_wrapper)
