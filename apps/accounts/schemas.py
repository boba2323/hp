from datetime import datetime

from ninja import ModelSchema, Schema

from apps.accounts.models import User


class UserOut(ModelSchema):
    full_name: str

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "phone",
            "is_active",
            "is_superuser",
            "last_login",
            "date_joined",
        ]


class UserCreateIn(ModelSchema):
    # Ninja's ModelSchema makes every ``blank=True`` field optional with a
    # default of None. These columns are NOT NULL, so an omitted field would
    # insert NULL and raise IntegrityError (a 500). Pin real defaults instead.
    password: str
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    phone: str = ""
    role: str = User.Role.RECEPTIONIST
    is_active: bool = True

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "phone",
            "is_active",
        ]


class UserUpdateIn(Schema):
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    role: str | None = None
    phone: str | None = None
    is_active: bool | None = None


class PasswordChangeIn(Schema):
    current_password: str
    new_password: str


class LoginIn(Schema):
    username: str
    password: str


class RefreshIn(Schema):
    refresh: str


class TokenOut(Schema):
    access: str
    refresh: str
    user: UserOut


class AccessTokenOut(Schema):
    access: str


class MeOut(UserOut):
    last_login: datetime | None = None
