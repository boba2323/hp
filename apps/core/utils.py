"""Request helpers shared by every router."""

from django.core.exceptions import FieldDoesNotExist
from django.http import Http404
from django.shortcuts import get_object_or_404 as _django_get_object_or_404
from ninja.errors import HttpError


def current_user(request):
    """Return the authenticated ``User`` set by ``JWTAuth``, or raise 401."""
    user = getattr(request, "auth", None)
    if user is None or not getattr(user, "is_authenticated", False):
        raise HttpError(401, "Authentication required")
    return user


def require_roles(request, *roles: str):
    """Return the current user, raising 403 unless they hold one of ``roles``.

    Superusers always pass.
    """
    user = current_user(request)
    if user.is_superuser or user.role in roles:
        return user
    raise HttpError(403, "You do not have permission to perform this action")


def get_object_or_404(model, *args, **kwargs):
    """Like Django's helper, but raises a Ninja ``HttpError`` instead of Http404."""
    try:
        return _django_get_object_or_404(model, *args, **kwargs)
    except Http404 as exc:
        raise HttpError(404, f"{model._meta.verbose_name.title()} not found") from exc


def drop_nullable_nulls(model, data: dict) -> dict:
    """Drop explicit ``None`` values aimed at columns that cannot store NULL.

    ``payload.model_dump(exclude_unset=True)`` keeps a key the client explicitly
    sent as ``null``. Most text columns here are ``blank=True`` but *not*
    ``null=True``, so writing that None raises IntegrityError and surfaces as a
    500. Dropping the key instead leaves the existing value in place, which is
    what "clear this field" reasonably means for a non-nullable text column.
    """
    cleaned = {}
    for field, value in data.items():
        if value is None:
            try:
                if not model._meta.get_field(field).null:
                    continue
            except FieldDoesNotExist:
                pass
        cleaned[field] = value
    return cleaned
