from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from apps.accounts.models import User


class HospitalUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "first_name", "last_name", "role")


class HospitalUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = HospitalUserCreationForm
    form = HospitalUserChangeForm
    list_display = (
        "username",
        "full_name",
        "email",
        "role",
        "phone",
        "is_active",
        "is_staff",
    )
    list_filter = ("role", "is_active", "is_staff", "is_superuser")
    search_fields = ("username", "first_name", "last_name", "email", "phone")
    ordering = ("first_name", "last_name")

    fieldsets = BaseUserAdmin.fieldsets + (
        ("Hospital", {"fields": ("role", "phone", "must_change_password")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (
            "Hospital",
            {
                "classes": ("wide",),
                "fields": ("email", "first_name", "last_name", "role", "phone"),
            },
        ),
    )

    @admin.display(description="Name")
    def full_name(self, obj):
        return obj.full_name
