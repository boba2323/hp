"""Pydantic schemas for departments and staff profiles."""

from datetime import date
from decimal import Decimal

from ninja import ModelSchema, Schema

from apps.accounts.models import User
from apps.staff.models import Department, StaffProfile

# Profile fields that live directly on ``StaffProfile`` (everything except the
# ``user``/``department`` relations and the generated ``employee_id``).
PROFILE_FIELDS = [
    "job_title",
    "employment_type",
    "specialty",
    "license_number",
    "hire_date",
    "date_of_birth",
    "gender",
    "address",
    "emergency_contact_name",
    "emergency_contact_phone",
    "consultation_fee",
    "is_available",
    "bio",
]


# --- Departments ------------------------------------------------------------


class DepartmentOut(ModelSchema):
    class Meta:
        model = Department
        fields = [
            "id",
            "name",
            "code",
            "description",
            "location",
            "phone",
            "is_active",
            "created_at",
        ]


class DepartmentIn(ModelSchema):
    # ``ModelSchema`` would default every blank model field to ``None``, but
    # these columns are NOT NULL - an omitted value has to arrive as "".
    description: str = ""
    location: str = ""
    phone: str = ""

    class Meta:
        model = Department
        fields = ["name", "code", "description", "location", "phone", "is_active"]


class DepartmentUpdateIn(Schema):
    name: str | None = None
    code: str | None = None
    description: str | None = None
    location: str | None = None
    phone: str | None = None
    is_active: bool | None = None


# --- Staff ------------------------------------------------------------------


class StaffUserOut(ModelSchema):
    """Minimal view of the login account behind a staff profile."""

    full_name: str

    class Meta:
        model = User
        fields = ["id", "username", "email", "role"]


class DepartmentBriefOut(ModelSchema):
    class Meta:
        model = Department
        fields = ["id", "name"]


class StaffOut(ModelSchema):
    user: StaffUserOut
    department: DepartmentBriefOut | None = None
    full_name: str
    role: str

    class Meta:
        model = StaffProfile
        fields = [
            "id",
            "employee_id",
            *PROFILE_FIELDS,
            "created_at",
            "updated_at",
        ]


class StaffIn(Schema):
    """Create payload - the account fields and the profile fields together.

    ``password`` is optional: when it is omitted a random temporary password is
    generated and ``must_change_password`` is set, so an administrator hands the
    account over through ``POST /api/auth/users/{id}/set-password``.
    """

    # --- inline account fields ---
    username: str
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    role: str = User.Role.RECEPTIONIST.value
    phone: str = ""
    password: str | None = None

    # --- profile fields ---
    employee_id: str | None = None
    department_id: int | None = None
    department: int | None = None
    job_title: str = ""
    employment_type: str = StaffProfile.EmploymentType.FULL_TIME.value
    specialty: str = ""
    license_number: str = ""
    hire_date: date | None = None
    date_of_birth: date | None = None
    gender: str = ""
    address: str = ""
    emergency_contact_name: str = ""
    emergency_contact_phone: str = ""
    consultation_fee: Decimal = Decimal("0.00")
    is_available: bool = True
    bio: str = ""


class StaffUpdateIn(Schema):
    """Partial update - account fields and profile fields are both accepted."""

    # --- inline account fields ---
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    role: str | None = None
    phone: str | None = None
    is_active: bool | None = None

    # --- profile fields ---
    employee_id: str | None = None
    department_id: int | None = None
    department: int | None = None
    job_title: str | None = None
    employment_type: str | None = None
    specialty: str | None = None
    license_number: str | None = None
    hire_date: date | None = None
    date_of_birth: date | None = None
    gender: str | None = None
    address: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    consultation_fee: Decimal | None = None
    is_available: bool | None = None
    bio: str | None = None


class DoctorOut(Schema):
    """Lightweight row for appointment booking selectors."""

    id: int
    full_name: str
    specialty: str
    department: str | None = None
    department_id: int | None = None
    consultation_fee: Decimal
