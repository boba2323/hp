"""Appointments API - booking, rescheduling and the visit lifecycle."""

from datetime import date, datetime

from django.db.models import Count, QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_date
from ninja import Router
from ninja.errors import HttpError

from apps.accounts.auth import jwt_auth
from apps.accounts.models import User
from apps.appointments.models import Appointment
from apps.appointments.schemas import (
    AppointmentCancelIn,
    AppointmentCreateIn,
    AppointmentOut,
    AppointmentUpdateIn,
)
from apps.core.pagination import apply_ordering, apply_search, paginate
from apps.core.schemas import MessageOut, Page
from apps.core.utils import current_user, get_object_or_404
from apps.patients.models import Patient
from apps.staff.models import Department, StaffProfile

router = Router(tags=["appointments"])

ORDERING_FIELDS = ["scheduled_start", "scheduled_end", "status", "created_at"]
SEARCH_FIELDS = [
    "patient__first_name",
    "patient__last_name",
    "patient__mrn",
    "doctor__user__first_name",
    "doctor__user__last_name",
]

# ``setattr`` on a ForeignKey needs the raw column name, not the relation name.
FK_ATTNAMES = {"patient": "patient_id", "doctor": "doctor_id", "department": "department_id"}

# Statuses that freed the doctor's calendar again.
RELEASED_STATUSES = [Appointment.Status.CANCELLED, Appointment.Status.NO_SHOW]

# Statuses that still hold a slot / may still be seen.
OPEN_STATUSES = [
    Appointment.Status.SCHEDULED,
    Appointment.Status.CONFIRMED,
    Appointment.Status.CHECKED_IN,
    Appointment.Status.IN_PROGRESS,
]

# Legal status moves. Completed / cancelled / no_show are terminal.
TRANSITIONS = {
    Appointment.Status.SCHEDULED: {
        Appointment.Status.CONFIRMED,
        Appointment.Status.CANCELLED,
        Appointment.Status.NO_SHOW,
    },
    Appointment.Status.CONFIRMED: {
        Appointment.Status.CHECKED_IN,
        Appointment.Status.CANCELLED,
        Appointment.Status.NO_SHOW,
    },
    Appointment.Status.CHECKED_IN: {
        Appointment.Status.IN_PROGRESS,
        Appointment.Status.CANCELLED,
        Appointment.Status.NO_SHOW,
    },
    Appointment.Status.IN_PROGRESS: {Appointment.Status.COMPLETED},
    Appointment.Status.COMPLETED: set(),
    Appointment.Status.CANCELLED: set(),
    Appointment.Status.NO_SHOW: set(),
}


# --- Helpers ----------------------------------------------------------------


def _base_queryset() -> QuerySet:
    """Everything a serialized appointment touches, fetched up front."""
    return Appointment.objects.select_related("patient", "doctor__user", "department")


def _get_appointment(appointment_id: int) -> Appointment:
    appointment = _base_queryset().filter(pk=appointment_id).first()
    if appointment is None:
        raise HttpError(404, "Appointment not found")
    return appointment


def _get_patient(patient_id: int) -> Patient:
    return get_object_or_404(Patient, pk=patient_id)


def _get_doctor(doctor_id: int) -> StaffProfile:
    """Resolve a ``StaffProfile`` and make sure it really belongs to a doctor."""
    doctor = StaffProfile.objects.select_related("user").filter(pk=doctor_id).first()
    if doctor is None:
        raise HttpError(404, "Staff profile not found")
    if doctor.user.role != User.Role.DOCTOR:
        raise HttpError(400, f"{doctor.full_name} is not a doctor")
    return doctor


def _assert_valid_choice(value: str | None, choices, field: str) -> None:
    if value is not None and value not in choices:
        raise HttpError(400, f"Invalid {field}: {value!r}")


def _validate_window(start: datetime | None, end: datetime | None) -> None:
    if start is None or end is None:
        raise HttpError(400, "scheduled_start and scheduled_end are required")
    if end <= start:
        raise HttpError(400, "scheduled_end must be after scheduled_start")


def _parse_iso_date(value: str, field: str) -> date:
    parsed = parse_date(value)
    if parsed is None:
        raise HttpError(400, f"Invalid {field}: {value!r} (expected YYYY-MM-DD)")
    return parsed


def _assert_no_conflict(
    doctor: StaffProfile,
    start: datetime,
    end: datetime,
    exclude_id: int | None = None,
) -> None:
    """Reject a window that overlaps another live appointment for this doctor.

    Cancelled and no-show rows no longer hold the slot, and the appointment
    being edited is excluded so a reschedule can keep its own window.
    """
    clashes = (
        Appointment.objects.filter(
            doctor=doctor,
            scheduled_start__lt=end,
            scheduled_end__gt=start,
        )
        .exclude(status__in=RELEASED_STATUSES)
        .order_by("scheduled_start")
    )
    if exclude_id is not None:
        clashes = clashes.exclude(pk=exclude_id)

    clash = clashes.first()
    if clash is not None:
        raise HttpError(
            409,
            f"Dr {doctor.full_name} already has an appointment from "
            f"{clash.scheduled_start:%Y-%m-%d %H:%M} to "
            f"{clash.scheduled_end:%Y-%m-%d %H:%M}",
        )


def _assert_transition(appointment: Appointment, target: str) -> None:
    if target not in TRANSITIONS.get(appointment.status, set()):
        raise HttpError(
            400,
            f"Cannot change an appointment from '{appointment.status}' to '{target}'",
        )


def _transition(appointment: Appointment, target: str) -> Appointment:
    _assert_transition(appointment, target)
    appointment.status = target
    appointment.save(update_fields=["status", "updated_at"])
    return appointment


# --- Fixed paths (registered before /{appointment_id}) ----------------------


@router.get("/today/", response=list[AppointmentOut], auth=jwt_auth)
def appointments_today(request):
    """Every appointment scheduled for the current local date."""
    return list(
        _base_queryset()
        .filter(scheduled_start__date=timezone.localdate())
        .order_by("scheduled_start")
    )


@router.get("/upcoming/", response=list[AppointmentOut], auth=jwt_auth)
def appointments_upcoming(request, limit: int = 10):
    """The next ``limit`` still-open appointments from now onwards."""
    limit = max(1, min(limit, 100))
    return list(
        _base_queryset()
        .filter(scheduled_start__gte=timezone.now(), status__in=OPEN_STATUSES)
        .order_by("scheduled_start")[:limit]
    )


@router.get("/stats/", auth=jwt_auth)
def appointment_stats(request, date_from: str | None = None, date_to: str | None = None):
    """Counts per status for an optional window, plus today's load."""
    queryset = Appointment.objects.all()
    if date_from:
        queryset = queryset.filter(
            scheduled_start__date__gte=_parse_iso_date(date_from, "date_from")
        )
    if date_to:
        queryset = queryset.filter(
            scheduled_start__date__lte=_parse_iso_date(date_to, "date_to")
        )

    by_status = {choice: 0 for choice, _label in Appointment.Status.choices}
    for row in queryset.values("status").annotate(total=Count("id")):
        by_status[row["status"]] = row["total"]

    return {
        "total": queryset.count(),
        "by_status": by_status,
        "today": Appointment.objects.filter(
            scheduled_start__date=timezone.localdate()
        ).count(),
        "date_from": date_from,
        "date_to": date_to,
    }


# --- Collection -------------------------------------------------------------


@router.get("/", response=Page[AppointmentOut], auth=jwt_auth)
def list_appointments(
    request,
    status: str | None = None,
    appointment_type: str | None = None,
    doctor: int | None = None,
    patient: int | None = None,
    department: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    queryset = _base_queryset()

    if status:
        queryset = queryset.filter(status=status)
    if appointment_type:
        queryset = queryset.filter(appointment_type=appointment_type)
    if doctor is not None:
        queryset = queryset.filter(doctor_id=doctor)
    if patient is not None:
        queryset = queryset.filter(patient_id=patient)
    if department is not None:
        queryset = queryset.filter(department_id=department)
    if date_from:
        queryset = queryset.filter(
            scheduled_start__date__gte=_parse_iso_date(date_from, "date_from")
        )
    if date_to:
        queryset = queryset.filter(
            scheduled_start__date__lte=_parse_iso_date(date_to, "date_to")
        )

    queryset = apply_search(queryset, request, SEARCH_FIELDS)
    queryset = apply_ordering(queryset, request, ORDERING_FIELDS, "-scheduled_start")
    return paginate(request, queryset, AppointmentOut)


@router.post("/", response={201: AppointmentOut}, auth=jwt_auth)
def create_appointment(request, payload: AppointmentCreateIn):
    data = payload.model_dump()

    _assert_valid_choice(
        data.get("appointment_type"), Appointment.Type.values, "appointment_type"
    )
    _validate_window(data["scheduled_start"], data["scheduled_end"])

    patient = _get_patient(data["patient"])
    doctor = _get_doctor(data["doctor"])
    department = (
        get_object_or_404(Department, pk=data["department"])
        if data.get("department") is not None
        else None
    )
    _assert_no_conflict(doctor, data["scheduled_start"], data["scheduled_end"])

    appointment = Appointment.objects.create(
        patient=patient,
        doctor=doctor,
        department=department,
        scheduled_start=data["scheduled_start"],
        scheduled_end=data["scheduled_end"],
        appointment_type=data["appointment_type"],
        reason=data["reason"],
        notes=data["notes"],
        created_by=current_user(request),
    )
    return 201, _get_appointment(appointment.pk)


# --- Single appointment -----------------------------------------------------


@router.get("/{int:appointment_id}", response=AppointmentOut, auth=jwt_auth)
def get_appointment(request, appointment_id: int):
    return _get_appointment(appointment_id)


@router.patch("/{int:appointment_id}", response=AppointmentOut, auth=jwt_auth)
def update_appointment(request, appointment_id: int, payload: AppointmentUpdateIn):
    appointment = _get_appointment(appointment_id)
    data = payload.model_dump(exclude_unset=True)

    _assert_valid_choice(
        data.get("appointment_type"), Appointment.Type.values, "appointment_type"
    )
    if data.get("patient") is not None:
        _get_patient(data["patient"])
    if data.get("department") is not None:
        get_object_or_404(Department, pk=data["department"])

    touches_schedule = bool({"doctor", "scheduled_start", "scheduled_end"} & data.keys())

    # Resolve the doctor and window that will actually be saved - the cached
    # relation on ``appointment`` still points at the pre-update values.
    doctor = (
        _get_doctor(data["doctor"])
        if data.get("doctor") is not None
        else appointment.doctor
    )
    start = data.get("scheduled_start") or appointment.scheduled_start
    end = data.get("scheduled_end") or appointment.scheduled_end
    _validate_window(start, end)
    if touches_schedule:
        _assert_no_conflict(doctor, start, end, exclude_id=appointment.pk)

    # ``department`` is the only nullable column here; a bare ``null`` for the
    # rest means "not supplied" rather than "blank the field out".
    for field, value in data.items():
        if value is None and field != "department":
            continue
        setattr(appointment, FK_ATTNAMES.get(field, field), value)

    appointment.save()
    return _get_appointment(appointment.pk)


@router.delete("/{int:appointment_id}", response=MessageOut, auth=jwt_auth)
def delete_appointment(request, appointment_id: int):
    appointment = _get_appointment(appointment_id)
    appointment.delete()
    return {"detail": "Appointment deleted"}


# --- Lifecycle actions ------------------------------------------------------


@router.post("/{int:appointment_id}/confirm", response=AppointmentOut, auth=jwt_auth)
def confirm_appointment(request, appointment_id: int):
    return _transition(_get_appointment(appointment_id), Appointment.Status.CONFIRMED)


@router.post("/{int:appointment_id}/check-in", response=AppointmentOut, auth=jwt_auth)
def check_in_appointment(request, appointment_id: int):
    return _transition(_get_appointment(appointment_id), Appointment.Status.CHECKED_IN)


@router.post("/{int:appointment_id}/start", response=AppointmentOut, auth=jwt_auth)
def start_appointment(request, appointment_id: int):
    return _transition(_get_appointment(appointment_id), Appointment.Status.IN_PROGRESS)


@router.post("/{int:appointment_id}/complete", response=AppointmentOut, auth=jwt_auth)
def complete_appointment(request, appointment_id: int):
    return _transition(_get_appointment(appointment_id), Appointment.Status.COMPLETED)


@router.post("/{int:appointment_id}/cancel", response=AppointmentOut, auth=jwt_auth)
def cancel_appointment(request, appointment_id: int, payload: AppointmentCancelIn):
    appointment = _get_appointment(appointment_id)
    _assert_transition(appointment, Appointment.Status.CANCELLED)

    appointment.status = Appointment.Status.CANCELLED
    appointment.cancellation_reason = payload.reason or ""
    appointment.save(update_fields=["status", "cancellation_reason", "updated_at"])
    return appointment


@router.post("/{int:appointment_id}/no-show", response=AppointmentOut, auth=jwt_auth)
def no_show_appointment(request, appointment_id: int):
    return _transition(_get_appointment(appointment_id), Appointment.Status.NO_SHOW)
