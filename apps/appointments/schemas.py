"""Schemas for the appointments app.

Plain ``Schema`` classes are used rather than ``ModelSchema`` so the JSON field
names match the model field names exactly: ``ModelSchema`` aliases foreign keys
to ``<name>_id`` on input, which would make the booking payload use
``patient_id``/``doctor_id`` instead of ``patient``/``doctor``.
"""

from datetime import datetime

from ninja import Schema

from apps.appointments.models import Appointment


class PatientBriefOut(Schema):
    """Patient summary embedded in an appointment."""

    id: int
    mrn: str
    full_name: str
    phone: str


class DoctorBriefOut(Schema):
    """Booked clinician - a ``staff.StaffProfile``."""

    id: int
    full_name: str
    specialty: str


class DepartmentBriefOut(Schema):
    id: int
    name: str


class AppointmentOut(Schema):
    id: int
    patient: PatientBriefOut
    doctor: DoctorBriefOut
    department: DepartmentBriefOut | None = None
    scheduled_start: datetime
    scheduled_end: datetime
    duration_minutes: int
    status: str
    appointment_type: str
    reason: str
    notes: str
    cancellation_reason: str
    created_at: datetime


class AppointmentCreateIn(Schema):
    patient: int
    doctor: int
    department: int | None = None
    scheduled_start: datetime
    scheduled_end: datetime
    appointment_type: str = Appointment.Type.SCHEDULED.value
    reason: str = ""
    notes: str = ""


class AppointmentUpdateIn(Schema):
    patient: int | None = None
    doctor: int | None = None
    department: int | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    appointment_type: str | None = None
    reason: str | None = None
    notes: str | None = None


class AppointmentCancelIn(Schema):
    reason: str = ""
