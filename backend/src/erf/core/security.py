"""Password hashing and token helpers."""

from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()

MIN_PASSWORD_LENGTH = 10


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Session tokens are stored hashed so a database leak does not expose live sessions."""
    return hashlib.sha256(token.encode()).hexdigest()


def password_problems(password: str) -> list[str]:
    problems: list[str] = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"Use at least {MIN_PASSWORD_LENGTH} characters.")
    if password.isalpha() or password.isdigit():
        problems.append("Mix letters with numbers or symbols.")
    return problems
