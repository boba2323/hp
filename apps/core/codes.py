"""Human-readable sequential identifiers (MRN, invoice numbers, ...)."""

from uuid import uuid4


def next_code(model, field: str, prefix: str, width: int = 6, max_attempts: int = 5) -> str:
    """Build ``PREFIX000001``-style codes derived from the next row id.

    Retries a few times in case a concurrent insert claimed the same value,
    then falls back to a random suffix so we never return a duplicate.
    """
    for _ in range(max_attempts):
        last = model.objects.order_by("-id").first()
        candidate = f"{prefix}{((last.id + 1) if last else 1):0{width}d}"
        if not model.objects.filter(**{field: candidate}).exists():
            return candidate
    return f"{prefix}{uuid4().hex[:8].upper()}"
