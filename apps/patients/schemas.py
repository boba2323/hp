"""Pydantic schemas for patient records."""

from datetime import date
from decimal import Decimal

from ninja import ModelSchema, Schema

from apps.patients.models import Patient

# Demographic/clinical fields a caller may set. ``mrn`` is generated, and
# ``registered_by`` is taken from the authenticated user.
WRITE_FIELDS = [
    "first_name",
    "last_name",
    "date_of_birth",
    "gender",
    "blood_group",
    "marital_status",
    "national_id",
    "phone",
    "alt_phone",
    "email",
    "address",
    "city",
    "state",
    "postal_code",
    "occupation",
    "allergies",
    "chronic_conditions",
    "emergency_contact_name",
    "emergency_contact_relationship",
    "emergency_contact_phone",
    "insurance_provider",
    "insurance_policy_number",
]


class PatientOut(ModelSchema):
    """Full record - everything clinical, demographic and administrative."""

    full_name: str
    age: int | None = None
    registered_by_id: int | None = None

    class Meta:
        model = Patient
        fields = [
            "id",
            "mrn",
            *WRITE_FIELDS,
            "is_active",
            "created_at",
            "updated_at",
        ]


class PatientListOut(ModelSchema):
    """Slim row for tables - no clinical free text."""

    full_name: str
    age: int | None = None

    class Meta:
        model = Patient
        fields = [
            "id",
            "mrn",
            "gender",
            "phone",
            "blood_group",
            "is_active",
            "created_at",
        ]


class PatientDetailOut(PatientOut):
    """Full record plus the counters and balance a chart needs on one page."""

    appointment_count: int = 0
    encounter_count: int = 0
    admission_count: int = 0
    invoice_count: int = 0
    outstanding_balance: Decimal = Decimal("0.00")


class PatientIn(ModelSchema):
    # ``ModelSchema`` would default every blank model field to ``None``, but
    # these columns are NOT NULL - an omitted value has to arrive as "".
    gender: str = ""
    blood_group: str = ""
    marital_status: str = ""
    phone: str = ""
    alt_phone: str = ""
    email: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    occupation: str = ""
    allergies: str = ""
    chronic_conditions: str = ""
    emergency_contact_name: str = ""
    emergency_contact_relationship: str = ""
    emergency_contact_phone: str = ""
    insurance_provider: str = ""
    insurance_policy_number: str = ""

    class Meta:
        model = Patient
        fields = WRITE_FIELDS


class PatientUpdateIn(Schema):
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None
    blood_group: str | None = None
    marital_status: str | None = None
    national_id: str | None = None
    phone: str | None = None
    alt_phone: str | None = None
    email: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    occupation: str | None = None
    allergies: str | None = None
    chronic_conditions: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_relationship: str | None = None
    emergency_contact_phone: str | None = None
    insurance_provider: str | None = None
    insurance_policy_number: str | None = None
    is_active: bool | None = None


class PatientLookupOut(Schema):
    """Minimal row for search/select boxes."""

    id: int
    mrn: str
    full_name: str
    age: int | None = None
    gender: str
    phone: str
