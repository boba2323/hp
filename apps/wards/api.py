"""Wards endpoints - wards, beds, occupancy and admissions.

Every literal first segment (``/beds/...``, ``/occupancy``, ``/admissions/...``)
is registered before the ``/{ward_id}`` routes: Django path converters match any
single segment, so a dynamic route declared first would swallow them.
"""

from datetime import date

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from ninja import Router
from ninja.errors import HttpError

from apps.accounts.auth import jwt_auth
from apps.accounts.models import User
from apps.core.pagination import apply_ordering, apply_search, paginate
from apps.core.schemas import MessageOut, Page
from apps.core.utils import current_user, get_object_or_404, require_roles
from apps.patients.models import Patient
from apps.staff.models import StaffProfile
from apps.wards.models import Admission, Bed, Ward
from apps.wards.schemas import (
    AdmissionIn,
    AdmissionOut,
    AdmissionUpdateIn,
    BedIn,
    BedOut,
    BedUpdateIn,
    DischargeIn,
    OccupancyOut,
    TransferIn,
    WardIn,
    WardOut,
    WardUpdateIn,
)

router = Router(tags=["wards"])

WARD_ORDERING = ["name", "code", "ward_type", "capacity", "charge_per_day"]
WARD_SEARCH = ["name", "code", "floor"]
BED_ORDERING = ["number", "status"]
BED_SEARCH = ["number", "ward__name", "ward__code"]
ADMISSION_ORDERING = ["admission_date", "discharge_date", "status", "created_at"]
ADMISSION_SEARCH = ["patient__first_name", "patient__last_name", "patient__mrn"]

WARD_ROLES = (User.Role.ADMIN, User.Role.NURSE, User.Role.RECEPTIONIST)
DISCHARGE_ROLES = (User.Role.ADMIN, User.Role.DOCTOR)


def _percentage(part: int, whole: int) -> float:
    return round(part / whole * 100, 1) if whole else 0.0


def _ensure_bed_available(bed: Bed) -> None:
    """A bed can only take a new patient when nothing else is using it."""
    if bed.status != Bed.Status.AVAILABLE or Admission.objects.filter(
        bed=bed, status=Admission.Status.ADMITTED
    ).exists():
        raise HttpError(400, f"Bed {bed.number} is not available")


def _release_bed_if_free(bed_id: int) -> None:
    """Hand a bed back to housekeeping once no admitted patient uses it.

    ``Admission.save()`` keeps the bed the patient is *on* in sync, but nothing
    frees a bed an admission was deleted from.
    """
    if Admission.objects.filter(
        bed_id=bed_id, status=Admission.Status.ADMITTED
    ).exists():
        return
    Bed.objects.filter(pk=bed_id, status=Bed.Status.OCCUPIED).update(
        status=Bed.Status.AVAILABLE
    )


# --- Wards ------------------------------------------------------------------


@router.get("/", response=Page[WardOut], auth=jwt_auth)
def list_wards(
    request,
    search: str | None = None,
    ward_type: str | None = None,
    is_active: bool | None = None,
):
    current_user(request)
    queryset = Ward.objects.all()

    if ward_type:
        queryset = queryset.filter(ward_type=ward_type)
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)

    queryset = apply_search(queryset, request, WARD_SEARCH)
    queryset = apply_ordering(queryset, request, WARD_ORDERING, "name")
    return paginate(request, queryset, WardOut)


@router.get("/beds/", response=Page[BedOut], auth=jwt_auth)
def list_beds(
    request,
    ward: int | None = None,
    status: str | None = None,
    search: str | None = None,
):
    """Every bed across the hospital, filterable by ward and status.

    Declared before `/{ward_id}` so the literal "beds" segment is not mistaken
    for a ward id.
    """
    current_user(request)
    queryset = Bed.objects.select_related("ward")

    if ward:
        queryset = queryset.filter(ward_id=ward)
    if status:
        queryset = queryset.filter(status=status)

    queryset = apply_search(queryset, request, BED_SEARCH)
    queryset = apply_ordering(queryset, request, BED_ORDERING, "ward__name")
    return paginate(request, queryset, BedOut)


@router.get("/beds/available", response=Page[BedOut], auth=jwt_auth)
def available_beds(request, ward: int | None = None):
    """Every bed a patient can be admitted to right now."""
    current_user(request)
    queryset = Bed.objects.select_related("ward").filter(status=Bed.Status.AVAILABLE)
    if ward:
        queryset = queryset.filter(ward_id=ward)

    queryset = apply_ordering(queryset, request, BED_ORDERING, "ward__name")
    return paginate(request, queryset, BedOut)


@router.get("/occupancy", response=OccupancyOut, auth=jwt_auth)
def occupancy(request):
    """Per-ward bed occupancy plus the hospital-wide roll-up."""
    current_user(request)
    rows = (
        Bed.objects.values("ward_id", "ward__name", "ward__code")
        .annotate(
            total_beds=Count("id"),
            occupied_beds=Count("id", filter=Q(status=Bed.Status.OCCUPIED)),
            available_beds=Count("id", filter=Q(status=Bed.Status.AVAILABLE)),
        )
        .order_by("ward__name")
    )

    wards = []
    total_beds = occupied_beds = available_beds = 0
    for row in rows:
        total_beds += row["total_beds"]
        occupied_beds += row["occupied_beds"]
        available_beds += row["available_beds"]
        wards.append(
            {
                "ward_id": row["ward_id"],
                "name": row["ward__name"],
                "code": row["ward__code"],
                "total_beds": row["total_beds"],
                "occupied_beds": row["occupied_beds"],
                "available_beds": row["available_beds"],
                "occupancy_percentage": _percentage(
                    row["occupied_beds"], row["total_beds"]
                ),
            }
        )

    return {
        "wards": wards,
        "total_beds": total_beds,
        "occupied_beds": occupied_beds,
        "available_beds": available_beds,
        "occupancy_percentage": _percentage(occupied_beds, total_beds),
    }


@router.get("/{int:ward_id}", response=WardOut, auth=jwt_auth)
def get_ward(request, ward_id: int):
    current_user(request)
    return get_object_or_404(Ward, pk=ward_id)


@router.post("/", response={201: WardOut}, auth=jwt_auth)
def create_ward(request, payload: WardIn):
    require_roles(request, *WARD_ROLES)
    data = payload.model_dump(exclude_unset=True, exclude_none=True)

    for field in ("name", "code"):
        if field in data and Ward.objects.filter(**{field: data[field]}).exists():
            raise HttpError(400, f"A ward with that {field} already exists")

    ward = Ward(**data)
    ward.save()
    return 201, ward


@router.patch("/{int:ward_id}", response=WardOut, auth=jwt_auth)
def update_ward(request, ward_id: int, payload: WardUpdateIn):
    require_roles(request, *WARD_ROLES)
    ward = get_object_or_404(Ward, pk=ward_id)

    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    for field in ("name", "code"):
        value = data.get(field)
        if value and Ward.objects.filter(**{field: value}).exclude(pk=ward.pk).exists():
            raise HttpError(400, f"A ward with that {field} already exists")

    for field, value in data.items():
        setattr(ward, field, value)
    ward.save()
    return ward


@router.delete("/{int:ward_id}", response=MessageOut, auth=jwt_auth)
def delete_ward(request, ward_id: int):
    """Refuses to remove a ward that still has beds (and their admission history)."""
    require_roles(request, *WARD_ROLES)
    ward = get_object_or_404(Ward, pk=ward_id)

    if ward.beds.exists():
        raise HttpError(
            400, f"{ward.name} still has {ward.bed_count} bed(s) attached"
        )
    if Admission.objects.filter(bed__ward=ward).exists():
        raise HttpError(400, f"{ward.name} has admission records and cannot be deleted")

    label = ward.name
    ward.delete()
    return {"detail": f"{label} deleted"}


@router.get("/{int:ward_id}/beds", response=Page[BedOut], auth=jwt_auth)
def list_ward_beds(request, ward_id: int, status: str | None = None):
    current_user(request)
    ward = get_object_or_404(Ward, pk=ward_id)
    queryset = ward.beds.select_related("ward")

    if status:
        queryset = queryset.filter(status=status)

    queryset = apply_ordering(queryset, request, BED_ORDERING, "number")
    return paginate(request, queryset, BedOut)


@router.post("/{int:ward_id}/beds", response={201: BedOut}, auth=jwt_auth)
def create_bed(request, ward_id: int, payload: BedIn):
    require_roles(request, *WARD_ROLES)
    ward = get_object_or_404(Ward, pk=ward_id)

    if Bed.objects.filter(ward=ward, number=payload.number).exists():
        raise HttpError(400, f"Bed {payload.number} already exists in {ward.name}")

    bed = Bed(ward=ward, **payload.model_dump(exclude_unset=True, exclude_none=True))
    bed.save()
    return 201, bed


@router.patch("/beds/{int:bed_id}", response=BedOut, auth=jwt_auth)
def update_bed(request, bed_id: int, payload: BedUpdateIn):
    require_roles(request, *WARD_ROLES)
    bed = get_object_or_404(Bed, pk=bed_id)

    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    number = data.get("number")
    if number and Bed.objects.filter(ward_id=bed.ward_id, number=number).exclude(
        pk=bed.pk
    ).exists():
        raise HttpError(400, f"Bed {number} already exists in {bed.ward.name}")

    for field, value in data.items():
        setattr(bed, field, value)
    bed.save()
    return bed


@router.delete("/beds/{int:bed_id}", response=MessageOut, auth=jwt_auth)
def delete_bed(request, bed_id: int):
    """Admission rows ``PROTECT`` their bed, so a used bed is never removed."""
    require_roles(request, *WARD_ROLES)
    bed = get_object_or_404(Bed, pk=bed_id)

    if bed.admissions.exists():
        raise HttpError(
            400, f"Bed {bed.number} has admission records and cannot be deleted"
        )

    label = str(bed)
    bed.delete()
    return {"detail": f"{label} deleted"}


# --- Admissions -------------------------------------------------------------


@router.get("/admissions/", response=Page[AdmissionOut], auth=jwt_auth)
def list_admissions(
    request,
    status: str | None = None,
    patient: int | None = None,
    ward: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
):
    current_user(request)
    queryset = Admission.objects.select_related(
        "patient", "bed__ward", "admitting_doctor__user"
    )

    if status:
        queryset = queryset.filter(status=status)
    if patient:
        queryset = queryset.filter(patient_id=patient)
    if ward:
        queryset = queryset.filter(bed__ward_id=ward)
    if date_from:
        queryset = queryset.filter(admission_date__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(admission_date__date__lte=date_to)

    queryset = apply_search(queryset, request, ADMISSION_SEARCH)
    queryset = apply_ordering(queryset, request, ADMISSION_ORDERING, "-admission_date")
    return paginate(request, queryset, AdmissionOut)


@router.get("/admissions/{int:admission_id}", response=AdmissionOut, auth=jwt_auth)
def get_admission(request, admission_id: int):
    current_user(request)
    return get_object_or_404(
        Admission.objects.select_related(
            "patient", "bed__ward", "admitting_doctor__user"
        ),
        pk=admission_id,
    )


@router.post("/admissions/", response={201: AdmissionOut}, auth=jwt_auth)
def create_admission(request, payload: AdmissionIn):
    """Admit a patient - the bed must be free, and ``save()`` marks it occupied."""
    require_roles(request, *WARD_ROLES)

    bed = get_object_or_404(Bed, pk=payload.bed)
    _ensure_bed_available(bed)
    patient = get_object_or_404(Patient, pk=payload.patient)
    doctor = get_object_or_404(StaffProfile, pk=payload.admitting_doctor)

    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    for field in ("patient", "bed", "admitting_doctor"):
        data.pop(field)
    data.setdefault("admission_date", timezone.now())

    admission = Admission(
        patient=patient, bed=bed, admitting_doctor=doctor, **data
    )
    admission.save()
    return 201, admission


@router.patch("/admissions/{int:admission_id}", response=AdmissionOut, auth=jwt_auth)
def update_admission(request, admission_id: int, payload: AdmissionUpdateIn):
    require_roles(request, *WARD_ROLES)
    admission = get_object_or_404(Admission, pk=admission_id)

    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "patient" in data:
        data["patient"] = get_object_or_404(Patient, pk=data["patient"])
    if "admitting_doctor" in data:
        data["admitting_doctor"] = get_object_or_404(
            StaffProfile, pk=data["admitting_doctor"]
        )

    for field, value in data.items():
        setattr(admission, field, value)
    admission.save()
    return admission


@router.delete("/admissions/{int:admission_id}", response=MessageOut, auth=jwt_auth)
def delete_admission(request, admission_id: int):
    require_roles(request, *WARD_ROLES)
    admission = get_object_or_404(Admission, pk=admission_id)

    bed_id = admission.bed_id
    label = str(admission)
    admission.delete()
    # Admission.save() never runs on delete, so free the bed ourselves.
    _release_bed_if_free(bed_id)
    return {"detail": f"Admission {label} deleted"}


@router.post(
    "/admissions/{int:admission_id}/discharge", response=AdmissionOut, auth=jwt_auth
)
def discharge_admission(
    request, admission_id: int, payload: DischargeIn | None = None
):
    """Close an admission - ``save()`` puts the bed back into rotation."""
    actor = require_roles(request, *DISCHARGE_ROLES)
    admission = get_object_or_404(Admission, pk=admission_id)

    if admission.status == Admission.Status.DISCHARGED:
        raise HttpError(400, "This admission has already been discharged")

    admission.status = Admission.Status.DISCHARGED
    admission.discharge_date = timezone.now()
    admission.discharged_by = actor
    if payload and payload.notes:
        admission.notes = f"{admission.notes}\n{payload.notes}".strip()
    admission.save()
    return admission


@router.post(
    "/admissions/{int:admission_id}/transfer",
    response={201: AdmissionOut},
    auth=jwt_auth,
)
def transfer_admission(request, admission_id: int, payload: TransferIn):
    """Move a patient to another bed: close the old admission, open a new one."""
    require_roles(request, *WARD_ROLES)
    admission = get_object_or_404(Admission, pk=admission_id)

    if admission.status != Admission.Status.ADMITTED:
        raise HttpError(
            400, f"Admission {admission.id} is not active and cannot be transferred"
        )

    new_bed = get_object_or_404(Bed, pk=payload.bed)
    if new_bed.pk == admission.bed_id:
        raise HttpError(400, f"Patient is already in bed {new_bed.number}")
    _ensure_bed_available(new_bed)

    with transaction.atomic():
        admission.status = Admission.Status.TRANSFERRED
        admission.save()

        transferred = Admission.objects.create(
            patient=admission.patient,
            bed=new_bed,
            admitting_doctor=admission.admitting_doctor,
            admission_date=timezone.now(),
            status=Admission.Status.ADMITTED,
            reason=admission.reason,
            notes=payload.notes or f"Transferred from bed {admission.bed.number}",
        )

    return 201, transferred
