from django.contrib import admin

from apps.appointments.models import Appointment


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "patient",
        "doctor",
        "department",
        "scheduled_start",
        "scheduled_end",
        "status",
        "appointment_type",
        "created_at",
    )
    list_filter = ("status", "appointment_type", "department", "scheduled_start")
    search_fields = (
        "patient__first_name",
        "patient__last_name",
        "patient__mrn",
        "doctor__user__first_name",
        "doctor__user__last_name",
        "reason",
    )
    autocomplete_fields = ("patient", "doctor", "department", "created_by")
    date_hierarchy = "scheduled_start"
    ordering = ("-scheduled_start",)
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("patient", "doctor__user", "department")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "patient",
                    "doctor",
                    "department",
                    "appointment_type",
                    "status",
                )
            },
        ),
        ("Schedule", {"fields": ("scheduled_start", "scheduled_end")}),
        ("Clinical", {"fields": ("reason", "notes", "cancellation_reason")}),
        ("Audit", {"fields": ("created_by", "created_at", "updated_at")}),
    )
