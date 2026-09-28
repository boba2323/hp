"""Records (EMR) API - encounters, diagnoses and prescriptions.

This is the clinical core of the system: everything here is append-mostly
evidence, so transitions are explicit and destructive operations are guarded.
"""

from datetime import date

from django.db.models import ProtectedError, QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_date
from ninja import Router
from ninja.errors import HttpError

from apps.accounts.auth import jwt_auth
from apps.accounts.models import User
from apps.appointments.models import Appointment
from apps.core.pagination import apply_ordering, apply_search, paginate
from apps.core.schemas import MessageOut, Page
from apps.core.utils import current_user, get_object_or_404, require_roles
from apps.patients.models import Patient
from apps.pharmacy.models import Medication
from apps.records.models import Diagnosis, Encounter, Prescription
from apps.records.schemas import (
    DiagnosisCreateIn,
    DiagnosisOut,
    DiagnosisUpdateIn,
    EncounterCreateIn,
    EncounterDetailOut,
    EncounterOut,
    EncounterUpdateIn,
    PrescriptionCreateIn,
    PrescriptionOut,
    PrescriptionUpdateIn,
)
from apps.staff.models import StaffProfile

router = Router(tags=["records"])

ORDERING_FIELDS = ["encounter_date", "created_at", "status"]
SEARCH_FIELDS = [
    "patient__first_name",
    "patient__last_name",
    "patient__mrn",
    "chief_complaint",
]

# ``setattr`` on a ForeignKey needs the raw column name, not the relation name.
FK_ATTNAMES = {
    "patient": "patient_id",
    "doctor": "doctor_id",
    "appointment": "appointment_id",
}

# Columns that may legitimately be set back to NULL by a PATCH.
NULLABLE_ENCOUNTER_FIELDS = {
    "appointment",
    "follow_up_date",
    "temperature_c",
    "bp_systolic",
    "bp_diastolic",
    "pulse",
    "respiratory_rate",
    "spo2",
    "weight_kg",
    "height_cm",
}


# --- Helpers ----------------------------------------------------------------


def _base_queryset() -> QuerySet:
    return Encounter.objects.select_related("patient", "doctor__user", "appointment")


def _get_encounter(encounter_id: int) -> Encounter:
    encounter = _base_queryset().filter(pk=encounter_id).first()
    if encounter is None:
        raise HttpError(404, "Encounter not found")
    return encounter


def _get_encounter_detail(encounter_id: int) -> Encounter:
    """An encounter with everything a detail response serializes."""
    encounter = (
        _base_queryset()
        .prefetch_related("diagnoses", "prescriptions__medication")
        .filter(pk=encounter_id)
        .first()
    )
    if encounter is None:
        raise HttpError(404, "Encounter not found")
    return encounter


def _get_diagnosis(diagnosis_id: int) -> Diagnosis:
    return get_object_or_404(Diagnosis, pk=diagnosis_id)


def _get_prescription(prescription_id: int) -> Prescription:
    prescription = (
        Prescription.objects.select_related("medication", "patient", "doctor__user")
        .filter(pk=prescription_id)
        .first()
    )
    if prescription is None:
        raise HttpError(404, "Prescription not found")
    return prescription


def _get_doctor(doctor_id: int) -> StaffProfile:
    doctor = StaffProfile.objects.select_related("user").filter(pk=doctor_id).first()
    if doctor is None:
        raise HttpError(404, "Staff profile not found")
    return doctor


def _assert_valid_choice(value: str | None, choices, field: str) -> None:
    if value is not None and value not in choices:
        raise HttpError(400, f"Invalid {field}: {value!r}")


def _parse_iso_date(value: str, field: str) -> date:
    parsed = parse_date(value)
    if parsed is None:
        raise HttpError(400, f"Invalid {field}: {value!r} (expected YYYY-MM-DD)")
    return parsed


def _assert_single_primary(encounter: Encounter, exclude_id: int | None = None) -> None:
    """An encounter carries at most one primary diagnosis."""
    existing = encounter.diagnoses.filter(diagnosis_type=Diagnosis.Type.PRIMARY)
    if exclude_id is not None:
        existing = existing.exclude(pk=exclude_id)
    if existing.exists():
        raise HttpError(400, "This encounter already has a primary diagnosis")


def _is_dispensed(prescription: Prescription) -> bool:
    """True once a ``pharmacy.Dispense`` row points at this prescription.

    Django makes the reverse-OneToOne's ``RelatedObjectDoesNotExist`` subclass
    ``AttributeError`` precisely so ``hasattr`` works here, and it answers from
    the related-object cache when the queryset prefetched it.
    """
    return hasattr(prescription, "dispense")


def _resolve_appointment(appointment_id: int, exclude_encounter_id: int | None = None):
    """An appointment can be attached to at most one encounter."""
    appointment = get_object_or_404(Appointment, pk=appointment_id)
    clashes = Encounter.objects.filter(appointment=appointment)
    if exclude_encounter_id is not None:
        clashes = clashes.exclude(pk=exclude_encounter_id)
    if clashes.exists():
        raise HttpError(400, "That appointment already has an encounter")
    return appointment


# --- Patient timeline (registered before /{encounter_id}) -------------------


@router.get("/patient/{int:patient_id}/history", response=list[EncounterDetailOut], auth=jwt_auth)
def patient_history(request, patient_id: int):
    """Chronological timeline for one patient - newest encounter first."""
    patient = get_object_or_404(Patient, pk=patient_id)
    encounters = (
        _base_queryset()
        .prefetch_related("diagnoses", "prescriptions__medication")
        .filter(patient=patient)
        .order_by("-encounter_date")
    )
    return list(encounters)


# --- Encounters -------------------------------------------------------------


@router.get("/", response=Page[EncounterOut], auth=jwt_auth)
def list_encounters(
    request,
    patient: int | None = None,
    doctor: int | None = None,
    encounter_type: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    queryset = _base_queryset()

    if patient is not None:
        queryset = queryset.filter(patient_id=patient)
    if doctor is not None:
        queryset = queryset.filter(doctor_id=doctor)
    if encounter_type:
        queryset = queryset.filter(encounter_type=encounter_type)
    if status:
        queryset = queryset.filter(status=status)
    if date_from:
        queryset = queryset.filter(
            encounter_date__date__gte=_parse_iso_date(date_from, "date_from")
        )
    if date_to:
        queryset = queryset.filter(
            encounter_date__date__lte=_parse_iso_date(date_to, "date_to")
        )

    queryset = apply_search(queryset, request, SEARCH_FIELDS)
    queryset = apply_ordering(queryset, request, ORDERING_FIELDS, "-encounter_date")
    return paginate(request, queryset, EncounterOut)


@router.post("/", response={201: EncounterOut}, auth=jwt_auth)
def create_encounter(request, payload: EncounterCreateIn):
    data = payload.model_dump()

    _assert_valid_choice(data.get("encounter_type"), Encounter.Type.values, "encounter_type")
    patient = get_object_or_404(Patient, pk=data.pop("patient"))
    doctor = _get_doctor(data.pop("doctor"))

    appointment_id = data.pop("appointment")
    appointment = (
        _resolve_appointment(appointment_id) if appointment_id is not None else None
    )

    # A visit that is being recorded now is dated now unless told otherwise.
    if data.get("encounter_date") is None:
        data["encounter_date"] = timezone.now()

    encounter = Encounter.objects.create(
        patient=patient,
        doctor=doctor,
        appointment=appointment,
        created_by=current_user(request),
        **data,
    )
    return 201, _get_encounter(encounter.pk)


@router.get("/{int:encounter_id}", response=EncounterDetailOut, auth=jwt_auth)
def get_encounter(request, encounter_id: int):
    return _get_encounter_detail(encounter_id)


@router.patch("/{int:encounter_id}", response=EncounterOut, auth=jwt_auth)
def update_encounter(request, encounter_id: int, payload: EncounterUpdateIn):
    encounter = _get_encounter(encounter_id)

    # A closed record is medicolegal evidence - only clinicians may amend it.
    if encounter.status == Encounter.Status.CLOSED:
        require_roles(request, User.Role.ADMIN, User.Role.DOCTOR)

    data = payload.model_dump(exclude_unset=True)

    _assert_valid_choice(data.get("encounter_type"), Encounter.Type.values, "encounter_type")
    _assert_valid_choice(data.get("status"), Encounter.Status.values, "status")

    if data.get("patient") is not None:
        get_object_or_404(Patient, pk=data["patient"])
    if data.get("doctor") is not None:
        _get_doctor(data["doctor"])
    appointment_id = data.get("appointment")
    if appointment_id is not None:
        _resolve_appointment(appointment_id, exclude_encounter_id=encounter.pk)

    for field, value in data.items():
        if value is None and field not in NULLABLE_ENCOUNTER_FIELDS:
            continue
        setattr(encounter, FK_ATTNAMES.get(field, field), value)

    encounter.save()
    return _get_encounter(encounter.pk)


@router.post("/{int:encounter_id}/close", response=EncounterOut, auth=jwt_auth)
def close_encounter(request, encounter_id: int):
    encounter = _get_encounter(encounter_id)
    encounter.status = Encounter.Status.CLOSED
    encounter.save(update_fields=["status", "updated_at"])
    return encounter


@router.delete("/{int:encounter_id}", response=MessageOut, auth=jwt_auth)
def delete_encounter(request, encounter_id: int):
    encounter = _get_encounter(encounter_id)
    try:
        encounter.delete()
    except ProtectedError as exc:
        raise HttpError(
            400, "This encounter has dispensed prescriptions and cannot be deleted"
        ) from exc
    return {"detail": "Encounter deleted"}


# --- Diagnoses (nested under an encounter) ----------------------------------


@router.get("/{int:encounter_id}/diagnoses", response=list[DiagnosisOut], auth=jwt_auth)
def list_diagnoses(request, encounter_id: int):
    encounter = _get_encounter(encounter_id)
    return list(encounter.diagnoses.all())


@router.post("/{int:encounter_id}/diagnoses", response={201: DiagnosisOut}, auth=jwt_auth)
def create_diagnosis(request, encounter_id: int, payload: DiagnosisCreateIn):
    encounter = _get_encounter(encounter_id)
    data = payload.model_dump()

    _assert_valid_choice(
        data.get("diagnosis_type"), Diagnosis.Type.values, "diagnosis_type"
    )
    if data["diagnosis_type"] == Diagnosis.Type.PRIMARY:
        _assert_single_primary(encounter)

    diagnosis = Diagnosis.objects.create(encounter=encounter, **data)
    return 201, diagnosis


@router.patch("/diagnoses/{int:diagnosis_id}", response=DiagnosisOut, auth=jwt_auth)
def update_diagnosis(request, diagnosis_id: int, payload: DiagnosisUpdateIn):
    diagnosis = _get_diagnosis(diagnosis_id)
    data = payload.model_dump(exclude_unset=True)

    _assert_valid_choice(
        data.get("diagnosis_type"), Diagnosis.Type.values, "diagnosis_type"
    )
    if data.get("diagnosis_type") == Diagnosis.Type.PRIMARY:
        _assert_single_primary(diagnosis.encounter, exclude_id=diagnosis.pk)

    for field, value in data.items():
        if value is None:
            continue
        setattr(diagnosis, field, value)
    diagnosis.save()
    return diagnosis


@router.delete("/diagnoses/{int:diagnosis_id}", response=MessageOut, auth=jwt_auth)
def delete_diagnosis(request, diagnosis_id: int):
    diagnosis = _get_diagnosis(diagnosis_id)
    diagnosis.delete()
    return {"detail": "Diagnosis deleted"}


# --- Prescriptions (nested under an encounter) ------------------------------


@router.get("/{int:encounter_id}/prescriptions", response=list[PrescriptionOut], auth=jwt_auth)
def list_prescriptions(request, encounter_id: int):
    encounter = _get_encounter(encounter_id)
    return list(encounter.prescriptions.select_related("medication"))


@router.post(
    "/{int:encounter_id}/prescriptions",
    response={201: PrescriptionOut},
    auth=jwt_auth,
)
def create_prescription(request, encounter_id: int, payload: PrescriptionCreateIn):
    encounter = _get_encounter(encounter_id)
    data = payload.model_dump()

    medication = get_object_or_404(Medication, pk=data.pop("medication"))

    # Patient and prescriber always come from the encounter, never the client.
    prescription = Prescription.objects.create(
        encounter=encounter,
        patient=encounter.patient,
        doctor=encounter.doctor,
        medication=medication,
        **data,
    )
    return 201, prescription


@router.patch("/prescriptions/{int:prescription_id}", response=PrescriptionOut, auth=jwt_auth)
def update_prescription(
    request, prescription_id: int, payload: PrescriptionUpdateIn
):
    prescription = _get_prescription(prescription_id)
    data = payload.model_dump(exclude_unset=True)

    _assert_valid_choice(data.get("status"), Prescription.Status.values, "status")

    medication_id = data.pop("medication", None)
    if medication_id is not None:
        prescription.medication = get_object_or_404(Medication, pk=medication_id)

    for field, value in data.items():
        if value is None:
            continue
        setattr(prescription, field, value)
    prescription.save()
    return prescription


@router.delete("/prescriptions/{int:prescription_id}", response=MessageOut, auth=jwt_auth)
def delete_prescription(request, prescription_id: int):
    prescription = _get_prescription(prescription_id)

    # A dispensed prescription is the pharmacy's audit trail - keep it.
    if _is_dispensed(prescription):
        raise HttpError(400, "This prescription has already been dispensed")

    prescription.delete()
    return {"detail": "Prescription deleted"}
