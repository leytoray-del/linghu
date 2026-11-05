"""Local account sign-in with server-side sessions, lockout after repeated failures, and password changes."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from erf.core.errors import Unauthorized, ValidationFailed
from erf.core.security import (
    hash_password,
    hash_token,
    needs_rehash,
    new_token,
    password_problems,
    verify_password,
)
from erf.db.models import User, UserSession
from erf.repositories.users import SessionRepository, UserRepository
from erf.services.context import ServiceContext

log = logging.getLogger(__name__)

INVALID_LOGIN = "The email or password is incorrect."


@dataclass(frozen=True, slots=True)
class IssuedSession:
    user: User
    token: str
    csrf_token: str
    expires_in_seconds: int


class AuthService:
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx
        self.users = UserRepository(ctx.session)
        self.sessions = SessionRepository(ctx.session)

    def login(self, email: str, password: str, *, user_agent: str | None, ip: str | None) -> IssuedSession:
        now = self.ctx.clock.now()
        user = self.users.get_by_email(email)
        if user is None or not user.is_active:
            verify_password(None, password)
            raise Unauthorized(INVALID_LOGIN)
        if user.locked_until and user.locked_until > now:
            minutes = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
            raise Unauthorized(
                f"This account is locked after too many failed attempts. Try again in {minutes} minutes."
            )
        if not verify_password(user.password_hash, password):
            user.failed_login_count += 1
            if user.failed_login_count >= self.ctx.settings.login_max_failures:
                user.locked_until = now + timedelta(minutes=self.ctx.settings.login_lockout_minutes)
                user.failed_login_count = 0
                log.warning("Account %s locked after repeated failed sign-ins", user.email)
            raise Unauthorized(INVALID_LOGIN)

        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = now
        if user.password_hash and needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        self.sessions.purge_expired(now)
        token = new_token()
        ttl = timedelta(hours=self.ctx.settings.session_ttl_hours)
        self.sessions.add(
            UserSession(
                token_hash=hash_token(token),
                user_id=user.id,
                created_at=now,
                expires_at=now + ttl,
                last_seen_at=now,
                user_agent=(user_agent or "")[:255] or None,
                ip_address=ip,
            )
        )
        return IssuedSession(user, token, new_token(), int(ttl.total_seconds()))

    def resolve(self, token: str | None) -> User | None:
        """Return the signed-in user for a session token and extend the session while it is in use."""
        if not token:
            return None
        row = self.sessions.get(hash_token(token))
        now = self.ctx.clock.now()
        if row is None or row.expires_at <= now or not row.user.is_active:
            return None
        ttl = timedelta(hours=self.ctx.settings.session_ttl_hours)
        if row.expires_at - now < ttl / 2:
            row.expires_at = now + ttl
        if (now - row.last_seen_at) > timedelta(minutes=5):
            row.last_seen_at = now
        return row.user

    def logout(self, token: str | None) -> None:
        if token:
            self.sessions.delete(hash_token(token))

    def change_password(self, user: User, current: str, new: str, *, keep_token: str | None) -> None:
        if not verify_password(user.password_hash, current):
            raise ValidationFailed(
                "Your current password is incorrect.",
                details={"fields": {"current_password": "Incorrect password."}},
            )
        problems = password_problems(new)
        if new == current:
            problems.append("Choose a password that is different from the current one.")
        if problems:
            raise ValidationFailed(
                " ".join(problems), details={"fields": {"new_password": " ".join(problems)}}
            )
        user.password_hash = hash_password(new)
        user.must_change_password = False
        self.sessions.delete_for_user(user.id, except_hash=hash_token(keep_token) if keep_token else None)
