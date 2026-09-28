"""Department and staff endpoints.

Mounted at ``/api/staff``. Departments live under ``/departments/``; the staff
profiles themselves (one per employee, wrapping an ``accounts.User``) live at
the router root.
"""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import transaction
from django.utils.crypto import get_random_string
from ninja import Router
from ninja.errors import HttpError

from apps.accounts.auth import jwt_auth
from apps.accounts.models import User
from apps.core.pagination import apply_ordering, apply_search, paginate
from apps.core.schemas import MessageOut, Page
from apps.core.utils import get_object_or_404, require_roles
from apps.staff.models import Department, StaffProfile
from apps.staff.schemas import (
    DepartmentIn,
    DepartmentOut,
    DepartmentUpdateIn,
    DoctorOut,
    StaffIn,
    StaffOut,
    StaffUpdateIn,
)

router = Router(tags=["staff"])

DEPARTMENT_SEARCH_FIELDS = ["name", "code"]
DEPARTMENT_ORDERING_FIELDS = ["name", "code", "created_at"]
STAFF_SEARCH_FIELDS = [
    "user__first_name",
    "user__last_name",
    "employee_id",
    "specialty",
    "license_number",
]
STAFF_ORDERING_FIELDS = [
    "employee_id",
    "hire_date",
    "created_at",
    "user__first_name",
    "user__last_name",
]

# Payload keys that belong on the nested ``User`` row rather than the profile.
# Everything else in a staff payload is written straight onto the profile.
USER_FIELDS = ("first_name", "last_name", "email", "phone", "role", "is_active")


def _staff_queryset():
    """Every staff read goes through here so nested rows never N+1."""
    return StaffProfile.objects.select_related("user", "department")


def _not_found():
    raise HttpError(404, "Staff profile not found")


def _next_employee_id() -> str:
    """``EMP-00001``-style identifier derived from the highest existing row id."""
    last = StaffProfile.objects.order_by("-id").first()
    next_id = (last.id + 1) if last else 1
    while StaffProfile.objects.filter(employee_id=f"EMP-{next_id:05d}").exists():
        next_id += 1
    return f"EMP-{next_id:05d}"


def _resolve_department(department_id: int | None) -> Department | None:
    if department_id is None:
        return None
    return get_object_or_404(Department, pk=department_id)


def _check_choice(value: str, choices, label: str) -> None:
    if value not in choices:
        raise HttpError(400, f"'{value}' is not a valid {label}")


def _department_id_from(payload_data: dict) -> int | None:
    """Accept both ``department_id`` and ``department`` (the model field name)."""
    department_id = payload_data.pop("department_id", None)
    alias = payload_data.pop("department", None)
    return department_id if department_id is not None else alias


def _allows_null(model, field_name: str) -> bool:
    try:
        return model._meta.get_field(field_name).null
    except FieldDoesNotExist:
        return True


# --- Departments ------------------------------------------------------------


@router.get("/departments/", response=Page[DepartmentOut], auth=jwt_auth)
def list_departments(
    request,
    is_active: bool | None = None,
    search: str | None = None,
):
    queryset = Department.objects.all()

    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)

    queryset = apply_search(queryset, request, DEPARTMENT_SEARCH_FIELDS)
    queryset = apply_ordering(queryset, request, DEPARTMENT_ORDERING_FIELDS, "name")
    return paginate(request, queryset, DepartmentOut)


@router.get("/departments/{int:department_id}", response=DepartmentOut, auth=jwt_auth)
def get_department(request, department_id: int):
    return get_object_or_404(Department, pk=department_id)


@router.post("/departments/", response={201: DepartmentOut}, auth=jwt_auth)
def create_department(request, payload: DepartmentIn):
    require_roles(request, User.Role.ADMIN)
    data = payload.model_dump()

    if Department.objects.filter(name=data["name"]).exists():
        raise HttpError(400, "A department with that name already exists")
    if Department.objects.filter(code=data["code"]).exists():
        raise HttpError(400, "A department with that code already exists")

    return 201, Department.objects.create(**data)


@router.patch("/departments/{int:department_id}", response=DepartmentOut, auth=jwt_auth)
def update_department(request, department_id: int, payload: DepartmentUpdateIn):
    require_roles(request, User.Role.ADMIN)
    department = get_object_or_404(Department, pk=department_id)
    data = payload.model_dump(exclude_unset=True)

    if "name" in data:
        clash = Department.objects.filter(name=data["name"]).exclude(pk=department.pk)
        if clash.exists():
            raise HttpError(400, "A department with that name already exists")
    if "code" in data:
        clash = Department.objects.filter(code=data["code"]).exclude(pk=department.pk)
        if clash.exists():
            raise HttpError(400, "A department with that code already exists")

    for field, value in data.items():
        # A null only ever clears a nullable column; the text columns are NOT NULL.
        if value is None and not _allows_null(Department, field):
            continue
        setattr(department, field, value)
    department.save()
    return department


@router.delete("/departments/{int:department_id}", response=MessageOut, auth=jwt_auth)
def deactivate_department(request, department_id: int):
    """Soft-delete a department.

    ``StaffProfile.department`` uses ``SET_NULL``, so a hard delete is allowed by
    the schema - but it would silently orphan every employee (and every historic
    appointment, encounter and admission) that was ever attached to the unit. We
    flip ``is_active`` instead: the department disappears from pickers while the
    existing links and their reporting stay intact.
    """
    require_roles(request, User.Role.ADMIN)
    department = get_object_or_404(Department, pk=department_id)

    department.is_active = False
    department.save(update_fields=["is_active"])
    return {"detail": f"{department.name} deactivated"}


# --- Doctors (literal path - must precede /{staff_id}) ----------------------


@router.get("/doctors/", response=list[DoctorOut], auth=jwt_auth)
def list_doctors(request):
    """Bookable doctors only - a flat list for appointment booking selectors."""
    queryset = (
        _staff_queryset()
        .filter(user__role=User.Role.DOCTOR, is_available=True)
        .order_by("user__first_name", "user__last_name")
    )
    return [
        DoctorOut(
            id=profile.id,
            full_name=profile.full_name,
            specialty=profile.specialty,
            department=profile.department.name if profile.department else None,
            department_id=profile.department_id,
            consultation_fee=profile.consultation_fee,
        )
        for profile in queryset
    ]


# --- Staff profiles ---------------------------------------------------------


@router.get("/", response=Page[StaffOut], auth=jwt_auth)
def list_staff(
    request,
    department: int | None = None,
    role: str | None = None,
    is_available: bool | None = None,
    search: str | None = None,
):
    queryset = _staff_queryset()

    if department is not None:
        queryset = queryset.filter(department_id=department)
    if role:
        queryset = queryset.filter(user__role=role)
    if is_available is not None:
        queryset = queryset.filter(is_available=is_available)

    queryset = apply_search(queryset, request, STAFF_SEARCH_FIELDS)
    queryset = apply_ordering(queryset, request, STAFF_ORDERING_FIELDS, "employee_id")
    return paginate(request, queryset, StaffOut)


@router.get("/{int:staff_id}", response=StaffOut, auth=jwt_auth)
def get_staff(request, staff_id: int):
    staff = _staff_queryset().filter(pk=staff_id).first() or _not_found()
    return staff


@router.post("/", response={201: StaffOut}, auth=jwt_auth)
def create_staff(request, payload: StaffIn):
    """Create the login account and its staff profile in one transaction.

    The ``User`` row is created with ``set_password`` and
    ``must_change_password=True``. When no password is supplied a random
    temporary one is generated; the administrator then sets a known value with
    ``POST /api/auth/users/{id}/set-password``.
    """
    require_roles(request, User.Role.ADMIN)
    data = payload.model_dump()

    account = {
        "username": data.pop("username"),
        "email": data.pop("email"),
        "first_name": data.pop("first_name"),
        "last_name": data.pop("last_name"),
        "role": data.pop("role"),
        "phone": data.pop("phone"),
    }
    password = data.pop("password", None)

    department = _resolve_department(_department_id_from(data))
    employee_id = data.pop("employee_id", None) or _next_employee_id()

    if User.objects.filter(username=account["username"]).exists():
        raise HttpError(400, "That username is already taken")
    _check_choice(account["role"], User.Role.values, "role")
    _check_choice(
        data["employment_type"],
        StaffProfile.EmploymentType.values,
        "employment type",
    )
    if StaffProfile.objects.filter(employee_id=employee_id).exists():
        raise HttpError(400, "That employee id is already in use")

    if password:
        try:
            validate_password(password)
        except ValidationError as exc:
            raise HttpError(400, " ".join(exc.messages)) from exc
    else:
        password = get_random_string(12)

    with transaction.atomic():
        user = User(**account)
        user.set_password(password)
        user.must_change_password = True
        user.save()

        staff = StaffProfile.objects.create(
            user=user,
            employee_id=employee_id,
            department=department,
            **data,
        )

    return 201, staff


@router.patch("/{int:staff_id}", response=StaffOut, auth=jwt_auth)
def update_staff(request, staff_id: int, payload: StaffUpdateIn):
    """Partial update - profile fields and nested ``User`` fields together."""
    require_roles(request, User.Role.ADMIN)
    staff = _staff_queryset().filter(pk=staff_id).first() or _not_found()
    data = payload.model_dump(exclude_unset=True)

    department_given = "department_id" in data or "department" in data
    department_id = _department_id_from(data)

    if "role" in data:
        _check_choice(data["role"], User.Role.values, "role")
    if "employment_type" in data:
        _check_choice(
            data["employment_type"],
            StaffProfile.EmploymentType.values,
            "employment type",
        )
    if "employee_id" in data:
        taken = StaffProfile.objects.filter(employee_id=data["employee_id"])
        if taken.exclude(pk=staff.pk).exists():
            raise HttpError(400, "That employee id is already in use")

    with transaction.atomic():
        if department_given:
            staff.department = _resolve_department(department_id)

        for field, value in data.items():
            model = User if field in USER_FIELDS else StaffProfile
            # A null only ever clears a nullable column; the rest are NOT NULL.
            if value is None and not _allows_null(model, field):
                continue
            if field in USER_FIELDS:
                setattr(staff.user, field, value)
            else:
                setattr(staff, field, value)

        staff.user.save()
        staff.save()

    return staff


@router.delete("/{int:staff_id}", response=MessageOut, auth=jwt_auth)
def deactivate_staff(request, staff_id: int):
    """Soft-delete a staff member.

    Staff are never hard deleted: appointments, encounters and admissions point
    at the profile (``PROTECT``) and the username has to stay traceable in the
    audit trail. We deactivate the underlying ``User`` so the login stops
    working and clear ``is_available`` so the profile drops out of booking
    selectors, while every historic row keeps its author.
    """
    actor = require_roles(request, User.Role.ADMIN)
    staff = _staff_queryset().filter(pk=staff_id).first() or _not_found()

    if staff.user_id == actor.pk:
        raise HttpError(400, "You cannot deactivate your own staff profile")

    staff.user.is_active = False
    staff.user.save(update_fields=["is_active"])
    staff.is_available = False
    staff.save(update_fields=["is_available"])

    return {"detail": f"{staff.full_name} deactivated"}
