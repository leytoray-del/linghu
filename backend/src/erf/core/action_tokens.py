"""Signed tokens for approve, return and reject links in emails.

A token names one approval task and an expiry time, signed with HMAC-SHA256. It carries no
permission by itself: the server still checks that the task is pending and acts as its assignee,
so a token stops working as soon as the task is handled.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TokenData:
    task_id: int
    expires: int
    """Unix timestamp (UTC seconds)."""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(secret: bytes, payload: bytes) -> str:
    return _b64(hmac.new(secret, payload, hashlib.sha256).digest())


def make_token(secret: bytes, task_id: int, expires: int) -> str:
    payload = f"{task_id}:{expires}".encode()
    return f"{_b64(payload)}.{_sign(secret, payload)}"


def read_token(secret: bytes, token: str) -> TokenData | None:
    """Return the token's data if the signature is valid, otherwise None. Expiry is checked by the caller."""
    try:
        encoded, signature = token.split(".", 1)
        payload = _unb64(encoded)
        if not hmac.compare_digest(signature, _sign(secret, payload)):
            return None
        task_id, expires = payload.decode().split(":", 1)
        return TokenData(int(task_id), int(expires))
    except (ValueError, UnicodeDecodeError):
        return None
