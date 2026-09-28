"""Laboratory API - test catalogue, order workflow and result capture."""

from datetime import date

from django.db import transaction
from django.db.models import Count, ProtectedError
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from ninja import Router
from ninja.errors import HttpError

from apps.accounts.auth import jwt_auth
from apps.core.pagination import apply_ordering, apply_search, paginate
from apps.core.schemas import MessageOut, Page
from apps.core.utils import current_user, drop_nullable_nulls, get_object_or_404
from apps.laboratory.models import LabOrder, LabOrderItem, LabTest
from apps.laboratory.schemas import (
    LabOrderCreateIn,
    LabOrderDetailOut,
    LabOrderItemResultIn,
    LabOrderOut,
    LabOrderUpdateIn,
    LabTestIn,
    LabTestOut,
    LabTestUpdateIn,
)
from apps.patients.models import Patient
from apps.records.models import Encounter
from apps.staff.models import StaffProfile

router = Router(tags=["laboratory"])

TEST_ORDERING_FIELDS = ["name", "code", "category", "price", "turnaround_hours"]
TEST_SEARCH_FIELDS = ["name", "code"]
ORDER_ORDERING_FIELDS = ["ordered_at", "status", "priority", "completed_at", "created_at"]
ORDER_SEARCH_FIELDS = [
    "patient__first_name",
    "patient__last_name",
    "patient__mrn",
    "items__test__name",
    "items__test__code",
]
CLOSED_STATUSES = {LabOrder.Status.COMPLETED, LabOrder.Status.CANCELLED}


# --- helpers ----------------------------------------------------------------


def _order_queryset():
    """Orders with everything the nested serializers need, no N+1."""
    return LabOrder.objects.select_related(
        "patient", "ordered_by__user"
    ).prefetch_related("items__test")


def _get_order(order_id: int) -> LabOrder:
    order = _order_queryset().filter(pk=order_id).first()
    if order is None:
        raise HttpError(404, "Lab order not found")
    return order


def _ensure_open(order: LabOrder, action: str) -> None:
    """Completed and cancelled orders are terminal - no further workflow moves."""
    if order.status in CLOSED_STATUSES:
        raise HttpError(
            400,
            f"Cannot {action} a {order.get_status_display().lower()} order",
        )


def _parse_bound(raw: str | None, label: str) -> date | None:
    """Accept ``YYYY-MM-DD`` (or a full ISO timestamp) and return a date."""
    if not raw:
        return None
    parsed = parse_date(raw)
    if parsed is None:
        moment = parse_datetime(raw)
        parsed = moment.date() if moment else None
    if parsed is None:
        raise HttpError(400, f"{label} must be an ISO date (YYYY-MM-DD)")
    return parsed


# --- test catalogue ---------------------------------------------------------


@router.get("/tests/", response=Page[LabTestOut], auth=jwt_auth)
def list_lab_tests(
    request,
    category: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
):
    queryset = LabTest.objects.all()

    if category:
        queryset = queryset.filter(category=category)
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)

    queryset = apply_search(queryset, request, TEST_SEARCH_FIELDS)
    queryset = apply_ordering(queryset, request, TEST_ORDERING_FIELDS, "name")
    return paginate(request, queryset, LabTestOut)


@router.post("/tests/", response={201: LabTestOut}, auth=jwt_auth)
def create_lab_test(request, payload: LabTestIn):
    data = payload.model_dump()

    if LabTest.objects.filter(name=data["name"]).exists():
        raise HttpError(400, "A test with that name already exists")
    if LabTest.objects.filter(code=data["code"]).exists():
        raise HttpError(400, "A test with that code already exists")

    return 201, LabTest.objects.create(**data)


@router.get("/tests/{int:test_id}", response=LabTestOut, auth=jwt_auth)
def get_lab_test(request, test_id: int):
    return get_object_or_404(LabTest, pk=test_id)


@router.patch("/tests/{int:test_id}", response=LabTestOut, auth=jwt_auth)
def update_lab_test(request, test_id: int, payload: LabTestUpdateIn):
    test = get_object_or_404(LabTest, pk=test_id)
    data = drop_nullable_nulls(LabTest, payload.model_dump(exclude_unset=True))

    if "name" in data and LabTest.objects.filter(name=data["name"]).exclude(pk=test.pk).exists():
        raise HttpError(400, "A test with that name already exists")
    if "code" in data and LabTest.objects.filter(code=data["code"]).exclude(pk=test.pk).exists():
        raise HttpError(400, "A test with that code already exists")

    for field, value in data.items():
        setattr(test, field, value)
    test.save()
    return test


@router.delete("/tests/{int:test_id}", response=MessageOut, auth=jwt_auth)
def delete_lab_test(request, test_id: int):
    """Remove a test from the catalogue.

    ``LabOrderItem.test`` is declared ``on_delete=PROTECT`` because past orders
    are clinical records: hard-deleting a test that was ever ordered would take
    those results with it. So when order history references the test we fall
    back to a soft delete (``is_active=False``) - it disappears from the
    ordering pickers while historical orders keep resolving.
    """
    test = get_object_or_404(LabTest, pk=test_id)

    if test.order_items.exists():
        test.is_active = False
        test.save(update_fields=["is_active"])
        return {
            "detail": (
                f"{test.name} is referenced by existing orders and was "
                "deactivated instead of deleted"
            )
        }

    name = test.name
    try:
        test.delete()
    except ProtectedError:
        # Raced with a new order between the check above and the delete.
        test.is_active = False
        test.save(update_fields=["is_active"])
        return {"detail": f"{name} was deactivated instead of deleted"}
    return {"detail": f"{name} deleted"}


# --- orders -----------------------------------------------------------------


@router.get("/orders/", response=Page[LabOrderOut], auth=jwt_auth)
def list_lab_orders(
    request,
    status: str | None = None,
    priority: str | None = None,
    patient: int | None = None,
    ordered_by: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None,
):
    queryset = _order_queryset()

    if status:
        queryset = queryset.filter(status=status)
    if priority:
        queryset = queryset.filter(priority=priority)
    if patient:
        queryset = queryset.filter(patient_id=patient)
    if ordered_by:
        queryset = queryset.filter(ordered_by_id=ordered_by)

    start = _parse_bound(date_from, "date_from")
    end = _parse_bound(date_to, "date_to")
    if start:
        queryset = queryset.filter(ordered_at__date__gte=start)
    if end:
        queryset = queryset.filter(ordered_at__date__lte=end)

    queryset = apply_search(queryset, request, ORDER_SEARCH_FIELDS)
    if (request.GET.get("search") or "").strip():
        # ORDER_SEARCH_FIELDS spans the reverse ``items`` relation, which
        # duplicates rows on the join.
        queryset = queryset.distinct()

    queryset = apply_ordering(queryset, request, ORDER_ORDERING_FIELDS, "-ordered_at")
    return paginate(request, queryset, LabOrderOut)


@router.get("/orders/pending", response=Page[LabOrderOut], auth=jwt_auth)
def pending_lab_orders(request):
    """The laboratory worklist - open orders, oldest first."""
    queryset = (
        _order_queryset()
        .exclude(status__in=list(CLOSED_STATUSES))
        .order_by("ordered_at")
    )
    return paginate(request, queryset, LabOrderOut)


@router.post("/orders/", response={201: LabOrderDetailOut}, auth=jwt_auth)
def create_lab_order(request, payload: LabOrderCreateIn):
    patient = get_object_or_404(Patient, pk=payload.patient)
    encounter = (
        get_object_or_404(Encounter, pk=payload.encounter) if payload.encounter else None
    )

    ordered_by_id = payload.ordered_by
    if ordered_by_id is None:
        # Fall back to the requesting user's own staff profile.
        try:
            staff_profile = current_user(request).staff_profile
        except StaffProfile.DoesNotExist:
            staff_profile = None
        if staff_profile is None:
            raise HttpError(400, "ordered_by is required")
        ordered_by_id = staff_profile.pk

    staff = get_object_or_404(StaffProfile, pk=ordered_by_id)

    tests = {test.pk: test for test in LabTest.objects.filter(pk__in=payload.test_ids)}
    missing = [test_id for test_id in payload.test_ids if test_id not in tests]
    if missing:
        raise HttpError(
            400, f"Unknown lab test id(s): {', '.join(str(m) for m in missing)}"
        )

    with transaction.atomic():
        order = LabOrder.objects.create(
            patient=patient,
            ordered_by=staff,
            encounter=encounter,
            priority=payload.priority,
            notes=payload.notes,
        )
        for test_id in payload.test_ids:
            # create() goes through LabOrderItem.save(), which snapshots the
            # catalogue price at the moment of ordering.
            LabOrderItem.objects.create(order=order, test=tests[test_id])

    return 201, _get_order(order.pk)


@router.get("/orders/{int:order_id}", response=LabOrderDetailOut, auth=jwt_auth)
def get_lab_order(request, order_id: int):
    return _get_order(order_id)


@router.patch("/orders/{int:order_id}", response=LabOrderDetailOut, auth=jwt_auth)
def update_lab_order(request, order_id: int, payload: LabOrderUpdateIn):
    order = _get_order(order_id)
    _ensure_open(order, "update")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(order, field, value)
    order.save()
    return _get_order(order_id)


@router.delete("/orders/{int:order_id}", response=MessageOut, auth=jwt_auth)
def delete_lab_order(request, order_id: int):
    """Delete an order that never produced results.

    Once a result has been recorded the order is part of the clinical record -
    cancel it (``POST /orders/{id}/cancel``) rather than erasing it.
    """
    order = _get_order(order_id)
    if order.has_results:
        raise HttpError(
            400, "Cannot delete an order with recorded results - cancel it instead"
        )

    order_id_value = order.pk
    order.delete()
    return {"detail": f"Lab order #{order_id_value} deleted"}


@router.post("/orders/{int:order_id}/collect", response=LabOrderDetailOut, auth=jwt_auth)
def collect_lab_order(request, order_id: int):
    """Sample has been taken - pending -> collected."""
    order = _get_order(order_id)
    _ensure_open(order, "collect")

    order.status = LabOrder.Status.COLLECTED
    order.save(update_fields=["status", "updated_at"])
    return order


@router.post("/orders/{int:order_id}/start", response=LabOrderDetailOut, auth=jwt_auth)
def start_lab_order(request, order_id: int):
    """Analysis has begun - collected -> in_progress."""
    order = _get_order(order_id)
    _ensure_open(order, "start")

    order.status = LabOrder.Status.IN_PROGRESS
    order.save(update_fields=["status", "updated_at"])
    return order


@router.post("/orders/{int:order_id}/cancel", response=LabOrderDetailOut, auth=jwt_auth)
def cancel_lab_order(request, order_id: int):
    """Abandon an order that has not reached a terminal state."""
    order = _get_order(order_id)
    _ensure_open(order, "cancel")

    order.status = LabOrder.Status.CANCELLED
    order.save(update_fields=["status", "updated_at"])
    return order


@router.post("/orders/{int:order_id}/results", response=LabOrderDetailOut, auth=jwt_auth)
def record_lab_order_results(
    request, order_id: int, payload: list[LabOrderItemResultIn]
):
    """Record results for one or more items of an order.

    ``LabOrderItem.save()`` flips the item to ``completed`` and stamps
    ``completed_at`` as soon as ``result_value`` is set, so we only assign the
    supplied fields and save. Once no item of the order is outstanding the
    order itself is completed and stamped. Re-submitting results for an already
    completed order is allowed (labs amend results); a cancelled order is not.
    """
    order = _get_order(order_id)
    if order.status == LabOrder.Status.CANCELLED:
        raise HttpError(400, "Cannot record results on a cancelled order")
    if not payload:
        raise HttpError(400, "No results supplied")

    with transaction.atomic():
        for entry in payload:
            item = order.items.filter(pk=entry.item).first()
            if item is None:
                raise HttpError(
                    404, f"Item {entry.item} does not belong to this order"
                )

            data = entry.model_dump(exclude_unset=True)
            data.pop("item", None)
            for field, value in data.items():
                setattr(item, field, value)
            item.save()

        outstanding = order.items.exclude(
            status__in=[LabOrderItem.Status.CANCELLED, LabOrderItem.Status.COMPLETED]
        )
        if order.items.exclude(status=LabOrderItem.Status.CANCELLED).exists() and not (
            outstanding.exists()
        ):
            order.status = LabOrder.Status.COMPLETED
            order.completed_at = order.completed_at or timezone.now()
            order.save(update_fields=["status", "completed_at", "updated_at"])

    return _get_order(order_id)


# --- statistics -------------------------------------------------------------


@router.get("/stats/", response=dict, auth=jwt_auth)
def lab_stats(request):
    """Counts by status, by priority and per test category ordered."""
    by_status = {value: 0 for value, _ in LabOrder.Status.choices}
    for row in LabOrder.objects.values("status").annotate(count=Count("id")):
        by_status[row["status"]] = row["count"]

    by_priority = {value: 0 for value, _ in LabOrder.Priority.choices}
    for row in LabOrder.objects.values("priority").annotate(count=Count("id")):
        by_priority[row["priority"]] = row["count"]

    by_category = {value: 0 for value, _ in LabTest.Category.choices}
    for row in LabOrderItem.objects.values("test__category").annotate(
        count=Count("id")
    ):
        by_category[row["test__category"]] = row["count"]

    return {
        "total_orders": LabOrder.objects.count(),
        "by_status": by_status,
        "by_priority": by_priority,
        "by_category": by_category,
    }
