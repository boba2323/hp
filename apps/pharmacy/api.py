"""Pharmacy endpoints - formulary, stock batches and dispensing.

Literal paths (``/low-stock/``, ``/expiring/``) are registered before the
``/{id}`` routes so they are never swallowed by a dynamic segment.
"""

from datetime import date, timedelta

from django.db import transaction
from django.db.models import F, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from ninja import Router
from ninja.errors import HttpError

from apps.accounts.auth import jwt_auth
from apps.accounts.models import User
from apps.core.pagination import apply_ordering, apply_search, paginate
from apps.core.schemas import MessageOut, Page
from apps.core.utils import current_user, get_object_or_404, require_roles
from apps.pharmacy.models import Dispense, Medication, StockBatch
from apps.pharmacy.schemas import (
    BatchIn,
    BatchOut,
    BatchUpdateIn,
    DispenseIn,
    DispenseOut,
    MedicationIn,
    MedicationOut,
    MedicationUpdateIn,
    PendingPrescriptionOut,
    StockOut,
)
from apps.records.models import Prescription

router = Router(tags=["pharmacy"])

MEDICATION_ORDERING = [
    "name",
    "generic_name",
    "brand_name",
    "category",
    "form",
    "unit_price",
    "reorder_level",
    "created_at",
]
MEDICATION_SEARCH = ["name", "generic_name", "brand_name"]
BATCH_ORDERING = ["expiry_date", "received_date", "batch_number", "quantity_remaining"]
PRESCRIPTION_SEARCH = [
    "patient__first_name",
    "patient__last_name",
    "patient__mrn",
    "medication__name",
    "doctor__user__first_name",
    "doctor__user__last_name",
]
DEFAULT_EXPIRY_WINDOW_DAYS = 90

STOCK_ROLES = (User.Role.ADMIN, User.Role.PHARMACIST)


def _with_stock(queryset):
    """Annotate ``stock`` with the units left across a medication's batches.

    ``Coalesce`` keeps medications that have no batches at all at 0 instead of
    ``NULL``, so they can be compared against ``reorder_level`` in SQL.
    """
    return queryset.annotate(
        stock=Coalesce(Sum("batches__quantity_remaining"), 0)
    )


# --- Medications ------------------------------------------------------------


@router.get("/medications/", response=Page[MedicationOut], auth=jwt_auth)
def list_medications(
    request,
    search: str | None = None,
    form: str | None = None,
    category: str | None = None,
    is_controlled: bool | None = None,
    is_active: bool | None = None,
    low_stock: bool = False,
):
    """Paginated formulary. ``?low_stock=true`` keeps rows at/below reorder level."""
    current_user(request)
    queryset = Medication.objects.all()

    if form:
        queryset = queryset.filter(form=form)
    if category:
        queryset = queryset.filter(category__iexact=category)
    if is_controlled is not None:
        queryset = queryset.filter(is_controlled=is_controlled)
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    if low_stock:
        queryset = _with_stock(queryset).filter(stock__lte=F("reorder_level"))

    queryset = apply_search(queryset, request, MEDICATION_SEARCH)
    queryset = apply_ordering(queryset, request, MEDICATION_ORDERING, "name")
    return paginate(request, queryset, MedicationOut)


@router.get("/low-stock/", response=Page[MedicationOut], auth=jwt_auth)
def list_low_stock(request):
    """Active medications whose remaining stock has hit the reorder level."""
    current_user(request)
    queryset = _with_stock(Medication.objects.filter(is_active=True)).filter(
        stock__lte=F("reorder_level")
    )
    queryset = apply_ordering(queryset, request, MEDICATION_ORDERING, "name")
    return paginate(request, queryset, MedicationOut)


@router.get("/expiring/", response=Page[BatchOut], auth=jwt_auth)
def list_expiring_batches(request, days: int = DEFAULT_EXPIRY_WINDOW_DAYS):
    """Batches that still hold stock and expire within ``?days=``, soonest first.

    Already-expired batches are not "expiring" - they are picked up by the
    ``is_expired`` flag on every batch payload instead.
    """
    current_user(request)
    days = max(1, min(days, 3650))
    today = timezone.localdate()
    queryset = (
        StockBatch.objects.select_related("medication")
        .filter(
            quantity_remaining__gt=0,
            expiry_date__isnull=False,
            expiry_date__gte=today,
            expiry_date__lte=today + timedelta(days=days),
        )
        .order_by("expiry_date", "id")
    )
    return paginate(request, queryset, BatchOut)


@router.get("/medications/{int:medication_id}", response=MedicationOut, auth=jwt_auth)
def get_medication(request, medication_id: int):
    current_user(request)
    return get_object_or_404(Medication, pk=medication_id)


@router.get(
    "/medications/{int:medication_id}/stock", response=StockOut, auth=jwt_auth
)
def medication_stock(request, medication_id: int):
    """Total stock, the per-batch breakdown and whether it is below reorder level."""
    current_user(request)
    medication = get_object_or_404(Medication, pk=medication_id)
    batches = medication.batches.select_related("medication").order_by(
        "expiry_date", "id"
    )
    total = sum(batch.quantity_remaining for batch in batches)
    return {
        "medication": medication,
        "total_stock": total,
        "reorder_level": medication.reorder_level,
        "is_low_stock": total <= medication.reorder_level,
        "batches": batches,
    }


@router.post("/medications/", response={201: MedicationOut}, auth=jwt_auth)
def create_medication(request, payload: MedicationIn):
    require_roles(request, *STOCK_ROLES)
    medication = Medication(
        **payload.model_dump(exclude_unset=True, exclude_none=True)
    )
    medication.save()
    return 201, medication


@router.patch("/medications/{int:medication_id}", response=MedicationOut, auth=jwt_auth)
def update_medication(request, medication_id: int, payload: MedicationUpdateIn):
    require_roles(request, *STOCK_ROLES)
    medication = get_object_or_404(Medication, pk=medication_id)
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in data.items():
        setattr(medication, field, value)
    medication.save()
    return medication


@router.delete("/medications/{int:medication_id}", response=MessageOut, auth=jwt_auth)
def deactivate_medication(request, medication_id: int):
    """Soft delete - the row is only flagged ``is_active=False``.

    ``records.Prescription.medication`` is a ``PROTECT`` foreign key, so a hard
    delete would raise ``ProtectedError`` for any drug that has ever been
    prescribed; deactivating also keeps the prescription history readable.
    """
    require_roles(request, *STOCK_ROLES)
    medication = get_object_or_404(Medication, pk=medication_id)
    medication.is_active = False
    medication.save(update_fields=["is_active", "updated_at"])
    return {"detail": f"{medication} deactivated"}


# --- Stock batches ----------------------------------------------------------


@router.get(
    "/medications/{int:medication_id}/batches", response=Page[BatchOut], auth=jwt_auth
)
def list_batches(request, medication_id: int):
    current_user(request)
    medication = get_object_or_404(Medication, pk=medication_id)
    queryset = medication.batches.select_related("medication")
    queryset = apply_ordering(queryset, request, BATCH_ORDERING, "expiry_date")
    return paginate(request, queryset, BatchOut)


@router.post(
    "/medications/{int:medication_id}/batches",
    response={201: BatchOut},
    auth=jwt_auth,
)
def create_batch(request, medication_id: int, payload: BatchIn):
    """Receive stock. ``quantity_remaining`` defaults to ``quantity_received``."""
    require_roles(request, *STOCK_ROLES)
    medication = get_object_or_404(Medication, pk=medication_id)

    if StockBatch.objects.filter(
        medication=medication, batch_number=payload.batch_number
    ).exists():
        raise HttpError(
            400,
            f"Batch {payload.batch_number} already exists for {medication.name}",
        )

    today = timezone.localdate()
    if payload.expiry_date and payload.expiry_date < today:
        raise HttpError(
            400, f"Expiry date {payload.expiry_date} is in the past"
        )

    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    if data.get("quantity_remaining") is None:
        data["quantity_remaining"] = payload.quantity_received

    batch = StockBatch(medication=medication, **data)
    batch.save()
    return 201, batch


@router.patch("/batches/{int:batch_id}", response=BatchOut, auth=jwt_auth)
def update_batch(request, batch_id: int, payload: BatchUpdateIn):
    require_roles(request, *STOCK_ROLES)
    batch = get_object_or_404(StockBatch, pk=batch_id)

    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    if data.get("expiry_date") and data["expiry_date"] < timezone.localdate():
        raise HttpError(400, f"Expiry date {data['expiry_date']} is in the past")

    for field, value in data.items():
        setattr(batch, field, value)
    batch.save()
    return batch


@router.delete("/batches/{int:batch_id}", response=MessageOut, auth=jwt_auth)
def delete_batch(request, batch_id: int):
    """A batch is only removable while no dispense points at it."""
    require_roles(request, *STOCK_ROLES)
    batch = get_object_or_404(StockBatch, pk=batch_id)

    if batch.dispenses.exists():
        raise HttpError(
            400,
            f"Batch {batch.batch_number} has dispense records and cannot be deleted",
        )

    label = f"{batch.medication.name} - {batch.batch_number}"
    batch.delete()
    return {"detail": f"{label} deleted"}


# --- Dispensing -------------------------------------------------------------


@router.get(
    "/prescriptions/pending", response=Page[PendingPrescriptionOut], auth=jwt_auth
)
def pending_prescriptions(request, search: str | None = None):
    """The pharmacist's work queue: prescriptions not yet handed out."""
    current_user(request)
    queryset = (
        Prescription.objects.select_related(
            "patient", "medication", "doctor__user"
        )
        .filter(status=Prescription.Status.PENDING)
        .order_by("created_at")
    )
    queryset = apply_search(queryset, request, PRESCRIPTION_SEARCH)
    return paginate(request, queryset, PendingPrescriptionOut)


@router.post("/dispense", response={201: DispenseOut}, auth=jwt_auth)
def dispense(request, payload: DispenseIn):
    """Hand a prescription's medication to the patient and draw down the batch.

    A batch is only accepted when it has enough units left; when none is given
    the earliest-expiring usable batch with enough stock is picked automatically.
    """
    actor = require_roles(request, *STOCK_ROLES)
    prescription = get_object_or_404(Prescription, pk=payload.prescription)

    if prescription.status == Prescription.Status.CANCELLED:
        raise HttpError(400, "This prescription has been cancelled")

    with transaction.atomic():
        try:
            Dispense.objects.get(prescription=prescription)
        except Dispense.DoesNotExist:
            pass
        else:
            raise HttpError(400, "This prescription has already been dispensed")

        quantity = payload.quantity_dispensed or prescription.quantity
        if quantity <= 0:
            raise HttpError(400, "Quantity dispensed must be greater than zero")

        if payload.batch:
            batch = get_object_or_404(
                StockBatch,
                pk=payload.batch,
                medication=prescription.medication,
            )
            batch = StockBatch.objects.select_for_update().get(pk=batch.pk)
        else:
            batch = _pick_batch(prescription, quantity)
            if batch is None:
                raise HttpError(
                    400,
                    f"No batch of {prescription.medication.name} has "
                    f"{quantity} units available",
                )

        if batch.quantity_remaining < quantity:
            raise HttpError(
                400,
                f"Batch {batch.batch_number} only has "
                f"{batch.quantity_remaining} units available",
            )

        batch.quantity_remaining -= quantity
        batch.save(update_fields=["quantity_remaining"])

        record = Dispense.objects.create(
            prescription=prescription,
            patient=prescription.patient,
            batch=batch,
            quantity_dispensed=quantity,
            dispensed_by=actor,
            notes=payload.notes,
        )

        prescription.status = (
            Prescription.Status.DISPENSED
            if quantity >= prescription.quantity
            else Prescription.Status.PARTIAL
        )
        prescription.save(update_fields=["status", "updated_at"])

    return 201, record


def _pick_batch(prescription, quantity: int):
    """Earliest-expiring usable batch of the prescribed drug with enough stock."""
    today = timezone.localdate()
    return (
        StockBatch.objects.select_for_update()
        .filter(
            medication=prescription.medication,
            quantity_remaining__gte=quantity,
        )
        .filter(Q(expiry_date__isnull=True) | Q(expiry_date__gte=today))
        .order_by(F("expiry_date").asc(nulls_last=True), "id")
        .first()
    )


@router.get("/dispenses", response=Page[DispenseOut], auth=jwt_auth)
def list_dispenses(
    request,
    patient: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
):
    """Dispensing history, newest first, filterable by patient and date range."""
    current_user(request)
    queryset = Dispense.objects.select_related(
        "patient",
        "batch",
        "dispensed_by",
        "prescription__medication",
    )

    if patient:
        queryset = queryset.filter(patient_id=patient)
    if date_from:
        queryset = queryset.filter(dispensed_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(dispensed_at__date__lte=date_to)

    return paginate(request, queryset, DispenseOut)
