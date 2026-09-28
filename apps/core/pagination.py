"""Offset pagination shared by every list endpoint.

Usage:
    data = paginate(request, queryset, PatientOut)
    return data            # validated against Page[PatientOut]
"""

from collections.abc import Sequence
from typing import Any

from django.core.paginator import EmptyPage, Paginator
from django.http import HttpRequest

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 200


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def paginate(
    request: HttpRequest,
    queryset: Sequence,
    schema: Any = None,
    page_size: int | None = None,
) -> dict:
    size = _as_int(request.GET.get("page_size"), page_size or DEFAULT_PAGE_SIZE)
    size = max(1, min(size, MAX_PAGE_SIZE))
    page_number = max(_as_int(request.GET.get("page"), 1), 1)

    paginator = Paginator(queryset, size)
    try:
        page = paginator.page(page_number)
    except EmptyPage:
        page = paginator.page(paginator.num_pages) if paginator.count else []

    results = list(page) if hasattr(page, "__iter__") else []
    if schema is not None:
        results = [schema.from_orm(obj) for obj in results]

    return {
        "count": paginator.count,
        "page": page_number,
        "page_size": size,
        "total_pages": paginator.num_pages,
        "results": results,
    }


def apply_ordering(queryset, request: HttpRequest, allowed: Sequence[str], default: str):
    """Apply ?ordering=field / ?ordering=-field, restricted to an allow-list."""
    raw = (request.GET.get("ordering") or "").strip()
    if not raw:
        return queryset.order_by(default)
    field = raw.lstrip("-")
    if field not in allowed:
        return queryset.order_by(default)
    return queryset.order_by(raw)


def apply_search(queryset, request: HttpRequest, fields: Sequence[str]):
    """Apply ?search=term across the given fields with OR semantics."""
    term = (request.GET.get("search") or "").strip()
    if not term:
        return queryset
    from django.db.models import Q

    query = Q()
    for field in fields:
        query |= Q(**{f"{field}__icontains": term})
    return queryset.filter(query)
