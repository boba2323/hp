"""Patient endpoints - mounted at ``/api/patients``."""

from decimal import Decimal

from django.core.exceptions import FieldDoesNotExist
from django.db.models import Count, Sum
from ninja import Router
from ninja.errors import HttpError

from apps.accounts.auth import jwt_auth
from apps.core.pagination import apply_ordering, apply_search, paginate
from apps.core.schemas import MessageOut, Page
from apps.core.utils import current_user, get_object_or_404
from apps.patients.models import Patient
from apps.patients.schemas import (
    PatientDetailOut,
    PatientIn,
    PatientListOut,
    PatientLookupOut,
    PatientOut,
    PatientUpdateIn,
)

router = Router(tags=["patients"])

SEARCH_FIELDS = ["mrn", "first_name", "last_name", "phone", "email", "national_id"]
ORDERING_FIELDS = ["mrn", "first_name", "last_name", "created_at"]
DEFAULT_ORDERING = "-created_at"

# Related sets that block a hard delete - a patient carrying any of these has a
# clinical/financial history that must survive.
CLINICAL_RELATIONS = ["encounters", "admissions", "invoices", "lab_orders"]

LOOKUP_LIMIT_DEFAULT = 20
LOOKUP_LIMIT_MAX = 100


def _not_found():
    raise HttpError(404, "Patient not found")


def _allows_null(model, field_name: str) -> bool:
    try:
        return model._meta.get_field(field_name).null
    except FieldDoesNotExist:
        return True


def _outstanding_balance(patient) -> Decimal:
    """Sum of the unpaid remainder across the patient's invoices."""
    from apps.billing.models import Invoice

    unpaid = Invoice.objects.filter(patient=patient, balance__gt=0)
    total = unpaid.aggregate(total=Sum("balance"))["total"]
    if total is None:
        return Decimal("0.00")
    # Backends differ on how a summed decimal comes back (SQLite hands back a
    # float-derived Decimal) - normalise so the API always speaks 2dp money.
    return Decimal(total).quantize(Decimal("0.01"))


# --- Lookup (literal path - must precede /{patient_id}) ---------------------


@router.get("/lookup/", response=list[PatientLookupOut], auth=jwt_auth)
def lookup_patients(request, search: str | None = None, limit: int = LOOKUP_LIMIT_DEFAULT):
    """Minimal active-patient rows for search and select boxes."""
    queryset = apply_search(Patient.objects.filter(is_active=True), request, SEARCH_FIELDS)

    size = max(1, min(limit, LOOKUP_LIMIT_MAX))
    queryset = queryset.order_by("first_name", "last_name")[:size]

    return [
        PatientLookupOut(
            id=patient.id,
            mrn=patient.mrn,
            full_name=patient.full_name,
            age=patient.age,
            gender=patient.gender,
            phone=patient.phone,
        )
        for patient in queryset
    ]


# --- Patients ---------------------------------------------------------------


@router.get("/", response=Page[PatientListOut], auth=jwt_auth)
def list_patients(
    request,
    gender: str | None = None,
    blood_group: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
):
    queryset = Patient.objects.all()

    if gender:
        queryset = queryset.filter(gender=gender)
    if blood_group:
        queryset = queryset.filter(blood_group=blood_group)
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)

    queryset = apply_search(queryset, request, SEARCH_FIELDS)
    queryset = apply_ordering(queryset, request, ORDERING_FIELDS, DEFAULT_ORDERING)
    return paginate(request, queryset, PatientListOut)


@router.get("/{int:patient_id}", response=PatientDetailOut, auth=jwt_auth)
def get_patient(request, patient_id: int):
    """Single patient with the chart counters in one query.

    The four ``Count`` annotations all traverse different reverse relations, so
    each one is ``distinct=True`` - without it the joins multiply each other and
    every count comes back inflated.
    """
    queryset = Patient.objects.annotate(
        appointment_count=Count("appointments", distinct=True),
        encounter_count=Count("encounters", distinct=True),
        admission_count=Count("admissions", distinct=True),
        invoice_count=Count("invoices", distinct=True),
    )
    patient = queryset.filter(pk=patient_id).first() or _not_found()
    patient.outstanding_balance = _outstanding_balance(patient)
    return patient


@router.post("/", response={201: PatientOut}, auth=jwt_auth)
def create_patient(request, payload: PatientIn):
    """Register a patient; ``registered_by`` is the authenticated user."""
    patient = Patient(**payload.model_dump(), registered_by=current_user(request))
    patient.save()
    return 201, patient


@router.patch("/{int:patient_id}", response=PatientOut, auth=jwt_auth)
def update_patient(request, patient_id: int, payload: PatientUpdateIn):
    patient = get_object_or_404(Patient, pk=patient_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        # A null only ever clears a nullable column; the text columns are NOT NULL.
        if value is None and not _allows_null(Patient, field):
            continue
        setattr(patient, field, value)
    patient.save()
    return patient


@router.post("/{int:patient_id}/deactivate", response=PatientOut, auth=jwt_auth)
def deactivate_patient(request, patient_id: int):
    """Soft "delete" for a patient who must stay in the records."""
    patient = get_object_or_404(Patient, pk=patient_id)

    patient.is_active = False
    patient.save(update_fields=["is_active"])
    return patient


@router.delete("/{int:patient_id}", response=MessageOut, auth=jwt_auth)
def delete_patient(request, patient_id: int):
    """Hard delete - only for a patient with no clinical or financial history.

    Encounters, admissions, invoices and lab orders all cascade from the patient
    row, so deleting someone who has any of them would silently destroy medical
    and billing records. Callers are told to deactivate instead.
    """
    patient = get_object_or_404(Patient, pk=patient_id)

    blocking = [name for name in CLINICAL_RELATIONS if getattr(patient, name).exists()]
    if blocking:
        raise HttpError(
            400,
            f"Patient {patient.mrn} has existing records ({', '.join(blocking)}) - "
            "deactivate the patient instead of deleting them",
        )

    patient.delete()
    return {"detail": f"Patient {patient.mrn} deleted"}
