from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from ninja import Router
from ninja.errors import HttpError

from apps.accounts.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    jwt_auth,
)
from apps.accounts.models import User
from apps.accounts.schemas import (
    AccessTokenOut,
    LoginIn,
    PasswordChangeIn,
    RefreshIn,
    TokenOut,
    UserCreateIn,
    UserOut,
    UserUpdateIn,
)
from apps.core.pagination import apply_ordering, apply_search, paginate
from apps.core.schemas import MessageOut, Page
from apps.core.utils import current_user, drop_nullable_nulls, require_roles

router = Router(tags=["auth"])

ORDERING_FIELDS = ["username", "first_name", "last_name", "role", "date_joined"]
SEARCH_FIELDS = ["username", "first_name", "last_name", "email", "phone"]


@router.post("/login", response=TokenOut, auth=None)
def login(request, payload: LoginIn):
    user = authenticate(
        request, username=payload.username, password=payload.password
    )
    if user is None:
        raise HttpError(401, "Invalid username or password")
    if not user.is_active:
        raise HttpError(403, "This account has been deactivated")

    return {
        "access": create_access_token(user),
        "refresh": create_refresh_token(user),
        "user": user,
    }


@router.post("/refresh", response=AccessTokenOut, auth=None)
def refresh(request, payload: RefreshIn):
    data = decode_token(payload.refresh, "refresh")
    if not data:
        raise HttpError(401, "Invalid or expired refresh token")

    user = User.objects.filter(pk=data["sub"], is_active=True).first()
    if user is None:
        raise HttpError(401, "User no longer active")

    return {"access": create_access_token(user)}


@router.get("/me", response=UserOut, auth=jwt_auth)
def me(request):
    return current_user(request)


@router.patch("/me", response=UserOut, auth=jwt_auth)
def update_me(request, payload: UserUpdateIn):
    user = current_user(request)
    data = drop_nullable_nulls(User, payload.model_dump(exclude_unset=True))
    # A user may not escalate their own role or reactivate themselves.
    data.pop("role", None)
    data.pop("is_active", None)
    for field, value in data.items():
        setattr(user, field, value)
    user.save()
    return user


@router.post("/change-password", response=MessageOut, auth=jwt_auth)
def change_password(request, payload: PasswordChangeIn):
    user = current_user(request)
    if not user.check_password(payload.current_password):
        raise HttpError(400, "Current password is incorrect")

    try:
        validate_password(payload.new_password, user)
    except ValidationError as exc:
        raise HttpError(400, " ".join(exc.messages)) from exc

    user.set_password(payload.new_password)
    user.must_change_password = False
    user.save(update_fields=["password", "must_change_password"])
    return {"detail": "Password updated"}


# --- User administration ----------------------------------------------------


@router.get("/users", response=Page[UserOut], auth=jwt_auth)
def list_users(
    request,
    role: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
):
    require_roles(request, User.Role.ADMIN)
    queryset = User.objects.all()

    if role:
        queryset = queryset.filter(role=role)
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)

    queryset = apply_search(queryset, request, SEARCH_FIELDS)
    queryset = apply_ordering(queryset, request, ORDERING_FIELDS, "first_name")
    return paginate(request, queryset, UserOut)


@router.get("/users/{int:user_id}", response=UserOut, auth=jwt_auth)
def get_user(request, user_id: int):
    require_roles(request, User.Role.ADMIN)
    return User.objects.filter(pk=user_id).first() or _not_found()


@router.post("/users", response={201: UserOut}, auth=jwt_auth)
def create_user(request, payload: UserCreateIn):
    require_roles(request, User.Role.ADMIN)

    if User.objects.filter(username=payload.username).exists():
        raise HttpError(400, "That username is already taken")

    data = payload.model_dump()
    password = data.pop("password")

    try:
        validate_password(password)
    except ValidationError as exc:
        raise HttpError(400, " ".join(exc.messages)) from exc

    user = User(**data)
    user.set_password(password)
    user.must_change_password = True
    user.save()
    return 201, user


@router.patch("/users/{int:user_id}", response=UserOut, auth=jwt_auth)
def update_user(request, user_id: int, payload: UserUpdateIn):
    require_roles(request, User.Role.ADMIN)
    user = User.objects.filter(pk=user_id).first() or _not_found()

    for field, value in drop_nullable_nulls(
        User, payload.model_dump(exclude_unset=True)
    ).items():
        setattr(user, field, value)
    user.save()
    return user


@router.post("/users/{int:user_id}/set-password", response=MessageOut, auth=jwt_auth)
def admin_set_password(request, user_id: int, payload: dict):
    require_roles(request, User.Role.ADMIN)
    user = User.objects.filter(pk=user_id).first() or _not_found()

    new_password = (payload or {}).get("new_password") or ""
    try:
        validate_password(new_password, user)
    except ValidationError as exc:
        raise HttpError(400, " ".join(exc.messages)) from exc

    user.set_password(new_password)
    user.must_change_password = True
    user.save(update_fields=["password", "must_change_password"])
    return {"detail": f"Password reset for {user.username}"}


@router.delete("/users/{int:user_id}", response=MessageOut, auth=jwt_auth)
def deactivate_user(request, user_id: int):
    """Soft-delete: staff accounts are never hard deleted (clinical audit trail)."""
    actor = require_roles(request, User.Role.ADMIN)
    user = User.objects.filter(pk=user_id).first() or _not_found()

    if user.pk == actor.pk:
        raise HttpError(400, "You cannot deactivate your own account")

    user.is_active = False
    user.save(update_fields=["is_active"])
    return {"detail": f"{user.username} deactivated"}


def _not_found():
    raise HttpError(404, "User not found")
