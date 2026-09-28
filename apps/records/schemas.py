"""Schemas for the records (EMR) app.

Plain ``Schema`` classes are used rather than ``ModelSchema`` because the
clinical payloads mix nested read-only summaries (patient, doctor, medication)
with computed properties (``blood_pressure``, ``bmi``) and nullable vitals;
declaring them keeps the JSON field names identical to the model field names.
"""

from datetime import date, datetime

from ninja import Schema

from apps.records.models import Diagnosis, Encounter


class PatientBriefOut(Schema):
    """Patient summary embedded in a clinical record."""

    id: int
    mrn: str
    full_name: str
    age: int | None = None
    gender: str


class DoctorBriefOut(Schema):
    id: int
    full_name: str
    specialty: str


class DiagnosisOut(Schema):
    id: int
    code: str
    description: str
    diagnosis_type: str
    notes: str
    created_at: datetime


class MedicationBriefOut(Schema):
    id: int
    name: str
    strength: str
    form: str


class PrescriptionOut(Schema):
    id: int
    encounter_id: int
    patient_id: int
    doctor_id: int
    medication: MedicationBriefOut
    dosage: str
    frequency: str
    route: str
    duration_days: int
    quantity: int
    instructions: str
    status: str
    created_at: datetime
    updated_at: datetime


class EncounterOut(Schema):
    id: int
    patient: PatientBriefOut
    doctor: DoctorBriefOut
    appointment_id: int | None = None
    encounter_type: str
    encounter_date: datetime
    chief_complaint: str
    history_of_present_illness: str
    examination_notes: str
    treatment_plan: str
    follow_up_date: date | None = None

    # Vitals
    temperature_c: float | None = None
    bp_systolic: int | None = None
    bp_diastolic: int | None = None
    pulse: int | None = None
    respiratory_rate: int | None = None
    spo2: int | None = None
    weight_kg: float | None = None
    height_cm: float | None = None

    # Computed
    blood_pressure: str | None = None
    bmi: float | None = None

    status: str
    created_at: datetime
    updated_at: datetime


class EncounterDetailOut(EncounterOut):
    """An encounter with its full clinical payload."""

    diagnoses: list[DiagnosisOut] = []
    prescriptions: list[PrescriptionOut] = []


class EncounterCreateIn(Schema):
    patient: int
    doctor: int
    appointment: int | None = None
    encounter_type: str = Encounter.Type.OUTPATIENT.value
    encounter_date: datetime | None = None
    chief_complaint: str = ""
    history_of_present_illness: str = ""
    examination_notes: str = ""
    treatment_plan: str = ""
    follow_up_date: date | None = None

    temperature_c: float | None = None
    bp_systolic: int | None = None
    bp_diastolic: int | None = None
    pulse: int | None = None
    respiratory_rate: int | None = None
    spo2: int | None = None
    weight_kg: float | None = None
    height_cm: float | None = None


class EncounterUpdateIn(Schema):
    patient: int | None = None
    doctor: int | None = None
    appointment: int | None = None
    encounter_type: str | None = None
    encounter_date: datetime | None = None
    chief_complaint: str | None = None
    history_of_present_illness: str | None = None
    examination_notes: str | None = None
    treatment_plan: str | None = None
    follow_up_date: date | None = None

    temperature_c: float | None = None
    bp_systolic: int | None = None
    bp_diastolic: int | None = None
    pulse: int | None = None
    respiratory_rate: int | None = None
    spo2: int | None = None
    weight_kg: float | None = None
    height_cm: float | None = None

    status: str | None = None


class DiagnosisCreateIn(Schema):
    code: str = ""
    description: str
    diagnosis_type: str = Diagnosis.Type.PRIMARY.value
    notes: str = ""


class DiagnosisUpdateIn(Schema):
    code: str | None = None
    description: str | None = None
    diagnosis_type: str | None = None
    notes: str | None = None


class PrescriptionCreateIn(Schema):
    medication: int
    dosage: str
    frequency: str
    route: str = "oral"
    duration_days: int = 1
    quantity: int = 1
    instructions: str = ""


class PrescriptionUpdateIn(Schema):
    medication: int | None = None
    dosage: str | None = None
    frequency: str | None = None
    route: str | None = None
    duration_days: int | None = None
    quantity: int | None = None
    instructions: str | None = None
    status: str | None = None
