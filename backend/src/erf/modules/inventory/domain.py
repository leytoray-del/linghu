"""Inventory rules: item states, the allowed actions, serial numbers and category fields."""

from __future__ import annotations

import re
from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ItemStatus(StrEnum):
    IN_STOCK = "IN_STOCK"
    """Registered and kept in a store."""
    REQUESTED = "REQUESTED"
    """In a withdrawal request waiting for approval; cannot be requested again."""
    DEPLOYED = "DEPLOYED"
    """Moved to its new location after the withdrawal was approved."""


class MovementKind(StrEnum):
    """Entries in an item's history."""

    RECEIVE = "RECEIVE"
    UPDATE = "UPDATE"
    REQUEST = "REQUEST"
    RELEASE = "RELEASE"
    DEPLOY = "DEPLOY"
    RETURN = "RETURN"
    DELETE = "DELETE"


class WithdrawalStatus(StrEnum):
    PENDING_PM = "PENDING_PM"
    PENDING_OM = "PENDING_OM"
    APPROVED = "APPROVED"
    RETURNED = "RETURNED"
    """Rejected and sent back to the requester, who can revise and resubmit it, or withdraw it."""
    WITHDRAWN = "WITHDRAWN"


class WithdrawalStep(StrEnum):
    PM = "PM"
    OM = "OM"


OPEN_WITHDRAWAL = frozenset(
    {WithdrawalStatus.PENDING_PM, WithdrawalStatus.PENDING_OM, WithdrawalStatus.RETURNED}
)

STATUS_TEXT: dict[ItemStatus, str] = {
    ItemStatus.IN_STOCK: "in stock",
    ItemStatus.REQUESTED: "in a withdrawal request",
    ItemStatus.DEPLOYED: "deployed",
}


def normalise_serial(value: str) -> str:
    """Serial numbers are compared in capitals, without spaces."""
    return re.sub(r"\s+", "", value).upper()


def serial_matches(pattern: str | None, serial: str) -> bool:
    if not pattern:
        return True
    try:
        return re.fullmatch(pattern, serial) is not None
    except re.error:
        return True


# ---- category fields ------------------------------------------------------------------------

FieldType = Literal["text", "number", "date", "choice", "boolean"]
_KEY = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


class FieldDef(BaseModel):
    key: str
    label: str = Field(min_length=1, max_length=60)
    type: FieldType
    choices: list[str] = Field(default_factory=list)
    required: bool = False
    show_in_list: bool = False
    retired: bool = False

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        if not _KEY.match(v):
            raise ValueError("Use lower-case letters, digits and underscores, starting with a letter.")
        return v

    @field_validator("choices")
    @classmethod
    def _choices(cls, v: list[str]) -> list[str]:
        cleaned = [c.strip() for c in v if c.strip()]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Each choice can appear only once.")
        return cleaned


def check_field_defs(new: list[FieldDef], old: list[FieldDef]) -> dict[str, str]:
    """Problems with a category's field list, keyed by field position. Keys and types never change once used."""
    problems: dict[str, str] = {}
    seen: set[str] = set()
    previous = {f.key: f for f in old}
    for i, f in enumerate(new):
        if f.key in seen:
            problems[f"fields.{i}.key"] = "Each field needs its own key."
        seen.add(f.key)
        if f.type == "choice" and not f.choices:
            problems[f"fields.{i}.choices"] = "Add at least one choice."
        before = previous.get(f.key)
        if before and before.type != f.type:
            problems[f"fields.{i}.type"] = "The type of a field cannot change. Retire it and add a new field."
    for key in previous:
        if key not in seen:
            problems["fields"] = (
                "Fields cannot be removed, because items may hold values for them. Retire them instead."
            )
    return problems


def clean_attributes(
    defs: list[FieldDef], values: dict[str, Any], *, require: bool
) -> tuple[dict[str, Any], dict[str, str]]:
    """Check values against the category's fields. Returns the cleaned values and any problems by field key."""
    by_key = {f.key: f for f in defs}
    cleaned: dict[str, Any] = {}
    problems: dict[str, str] = {}
    for key, raw in values.items():
        f = by_key.get(key)
        if f is None:
            problems[key] = "This field does not belong to the category."
            continue
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            continue
        try:
            cleaned[key] = _convert(f, raw)
        except ValueError as exc:
            problems[key] = str(exc)
    if require:
        for f in defs:
            if f.required and not f.retired and f.key not in cleaned and f.key not in problems:
                problems[f.key] = f"{f.label} is required."
    return cleaned, problems


def _convert(f: FieldDef, raw: Any) -> Any:
    if f.type == "text":
        text = str(raw).strip()
        if len(text) > 200:
            raise ValueError("Use no more than 200 characters.")
        return text
    if f.type == "number":
        try:
            number = float(raw)
        except (TypeError, ValueError):
            raise ValueError("Enter a number.") from None
        return int(number) if number.is_integer() else number
    if f.type == "date":
        if isinstance(raw, date):
            return raw.isoformat()
        try:
            return date.fromisoformat(str(raw).strip()[:10]).isoformat()
        except ValueError:
            raise ValueError("Enter a valid date.") from None
    if f.type == "choice":
        text = str(raw).strip()
        match = next((c for c in f.choices if c.lower() == text.lower()), None)
        if match is None:
            raise ValueError("Choose one of: " + ", ".join(f.choices) + ".")
        return match
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in ("yes", "y", "true", "1"):
        return True
    if text in ("no", "n", "false", "0"):
        return False
    raise ValueError("Choose yes or no.")
