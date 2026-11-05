from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(Schema, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class ErrorBody(Schema):
    code: str
    message: str
    details: dict[str, object] = {}


class UserRef(Schema):
    id: int
    display_name: str
    email: str
    job_title: str | None = None


class Message(Schema):
    message: str
