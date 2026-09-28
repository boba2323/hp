"""Schemas shared by every app."""

from ninja import Schema


class Page[T](Schema):
    """Uniform paginated envelope returned by every list endpoint."""

    count: int
    page: int
    page_size: int
    total_pages: int
    results: list[T]


class MessageOut(Schema):
    """Generic acknowledgement for endpoints that have nothing else to say."""

    detail: str
