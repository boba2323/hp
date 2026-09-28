from django.contrib import admin

from apps.wards.models import Admission, Bed, Ward


@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "code",
        "ward_type",
        "floor",
        "capacity",
        "charge_per_day",
        "is_active",
    ]
    list_filter = ["ward_type", "is_active", "floor"]
    search_fields = ["name", "code", "floor"]
    readonly_fields = ["created_at"]


@admin.register(Bed)
class BedAdmin(admin.ModelAdmin):
    list_display = ["number", "ward", "status", "notes"]
    list_filter = ["status", "ward"]
    search_fields = ["number", "ward__name", "ward__code"]
    autocomplete_fields = ["ward"]


@admin.register(Admission)
class AdmissionAdmin(admin.ModelAdmin):
    list_display = [
        "patient",
        "bed",
        "admitting_doctor",
        "admission_date",
        "discharge_date",
        "status",
    ]
    list_filter = ["status", "admission_date", "bed__ward"]
    search_fields = [
        "patient__first_name",
        "patient__last_name",
        "patient__mrn",
        "bed__number",
    ]
    autocomplete_fields = ["patient", "bed", "admitting_doctor", "discharged_by"]
    readonly_fields = ["created_at", "updated_at"]
    date_hierarchy = "admission_date"
