from django.contrib import admin

from apps.patients.models import Patient


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = [
        "mrn",
        "full_name",
        "gender",
        "age",
        "phone",
        "blood_group",
        "is_active",
        "created_at",
    ]
    list_filter = ["is_active", "gender", "blood_group", "marital_status"]
    search_fields = [
        "mrn",
        "first_name",
        "last_name",
        "phone",
        "email",
        "national_id",
    ]
    autocomplete_fields = ["registered_by"]
    readonly_fields = ["mrn", "created_at", "updated_at"]
    list_select_related = ["registered_by"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]

    @admin.display(description="Name", ordering="last_name")
    def full_name(self, obj):
        return obj.full_name

    @admin.display(description="Age", ordering="date_of_birth")
    def age(self, obj):
        return obj.age
