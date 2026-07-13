from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Optional


class AuthError(RuntimeError):
    """Raised when a login token or credential cannot be trusted."""


@dataclass(frozen=True)
class DemoAccount:
    user_id: str
    username: str
    password_hash: str
    display_name: str
    tenant_id: str
    department: str
    role: str


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


DEMO_ACCOUNTS: dict[str, DemoAccount] = {
    "local-demo": DemoAccount(
        user_id="local-demo",
        username="local-demo",
        password_hash=_hash_password("demo123456"),
        display_name="Local Demo",
        tenant_id="tenant-demo",
        department="compliance",
        role="owner",
    ),
    "alice": DemoAccount(
        user_id="demo-alice",
        username="alice",
        password_hash=_hash_password("alice123456"),
        display_name="Alice",
        tenant_id="tenant-demo",
        department="sales",
        role="editor",
    ),
    "bob": DemoAccount(
        user_id="demo-bob",
        username="bob",
        password_hash=_hash_password("bob123456"),
        display_name="Bob",
        tenant_id="tenant-demo",
        department="legal",
        role="viewer",
    ),
}


def authenticate_demo_user(username: str, password: str) -> Optional[DemoAccount]:
    account = DEMO_ACCOUNTS.get(username.strip())
    if account is None:
        return None
    if not hmac.compare_digest(account.password_hash, _hash_password(password)):
        return None
    return account


def account_by_user_id(user_id: str) -> Optional[DemoAccount]:
    return next((account for account in DEMO_ACCOUNTS.values() if account.user_id == user_id), None)


def create_access_token(account: DemoAccount, expires_in_seconds: int = 8 * 60 * 60) -> str:
    now = int(time.time())
    payload = {
        "sub": account.user_id,
        "name": account.display_name,
        "tenant_id": account.tenant_id,
        "department": account.department,
        "role": account.role,
        "iat": now,
        "exp": now + expires_in_seconds,
    }
    return _encode_jwt(payload)


def verify_access_token(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError("Invalid token")
    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    expected_signature = _sign(signing_input)
    actual_signature = _base64url_decode(parts[2])
    if not hmac.compare_digest(actual_signature, expected_signature):
        raise AuthError("Invalid token signature")
    try:
        payload = json.loads(_base64url_decode(parts[1]))
    except (ValueError, UnicodeDecodeError) as exc:
        raise AuthError("Invalid token payload") from exc
    if int(payload.get("exp", 0)) < int(time.time()):
        raise AuthError("Token expired")
    if not payload.get("sub"):
        raise AuthError("Token is missing subject")
    return payload


def _encode_jwt(payload: dict[str, Any]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _base64url_json(header)
    encoded_payload = _base64url_json(payload)
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = _base64url_encode(_sign(signing_input))
    return f"{encoded_header}.{encoded_payload}.{signature}"


def _sign(signing_input: bytes) -> bytes:
    return hmac.new(_jwt_secret(), signing_input, hashlib.sha256).digest()


def _jwt_secret() -> bytes:
    return os.getenv("JWT_SECRET", "dev-only-change-me").encode("utf-8")


def _base64url_json(payload: dict[str, Any]) -> str:
    return _base64url_encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))
