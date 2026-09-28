from django.contrib import admin

from apps.records.models import Diagnosis, Encounter, Prescription


class DiagnosisInline(admin.TabularInline):
    model = Diagnosis
    extra = 1


class PrescriptionInline(admin.TabularInline):
    model = Prescription
    extra = 1


@admin.register(Encounter)
class EncounterAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "patient",
        "doctor",
        "encounter_date",
        "encounter_type",
        "status",
        "blood_pressure",
        "bmi",
        "created_at",
    )
    list_filter = ("status", "encounter_type", "encounter_date", "doctor__department")
    search_fields = (
        "patient__first_name",
        "patient__last_name",
        "patient__mrn",
        "doctor__user__first_name",
        "doctor__user__last_name",
    )
    autocomplete_fields = ("patient", "doctor", "appointment", "created_by")
    date_hierarchy = "encounter_date"
    ordering = ("-encounter_date",)
    readonly_fields = (
        "blood_pressure",
        "bmi",
        "created_at",
        "updated_at",
    )
    list_select_related = ("patient", "doctor__user")
    inlines = (DiagnosisInline, PrescriptionInline)
    fieldsets = (
        (None, {"fields": ("patient", "doctor", "appointment", "encounter_type", "encounter_date", "status")}),
        (
            "History",
            {
                "fields": (
                    "chief_complaint",
                    "history_of_present_illness",
                    "examination_notes",
                    "treatment_plan",
                    "follow_up_date",
                )
            },
        ),
        (
            "Vitals",
            {
                "fields": (
                    "temperature_c",
                    "bp_systolic",
                    "bp_diastolic",
                    "blood_pressure",
                    "pulse",
                    "respiratory_rate",
                    "spo2",
                    "weight_kg",
                    "height_cm",
                    "bmi",
                )
            },
        ),
        ("Audit", {"fields": ("created_by", "created_at", "updated_at")}),
    )

    @admin.display(description="BP")
    def blood_pressure(self, obj):
        return obj.blood_pressure

    @admin.display(description="BMI")
    def bmi(self, obj):
        return obj.bmi


@admin.register(Diagnosis)
class DiagnosisAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "encounter",
        "code",
        "description",
        "diagnosis_type",
        "created_at",
    )
    list_filter = ("diagnosis_type", "created_at")
    search_fields = (
        "code",
        "description",
        "encounter__patient__first_name",
        "encounter__patient__last_name",
        "encounter__patient__mrn",
    )
    autocomplete_fields = ("encounter",)
    ordering = ("diagnosis_type", "id")
    list_select_related = ("encounter", "encounter__patient")


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "patient",
        "medication",
        "dosage",
        "frequency",
        "duration_days",
        "quantity",
        "status",
        "created_at",
    )
    list_filter = ("status", "route", "created_at")
    search_fields = (
        "medication__name",
        "medication__generic_name",
        "patient__first_name",
        "patient__last_name",
        "patient__mrn",
        "doctor__user__first_name",
        "doctor__user__last_name",
    )
    autocomplete_fields = ("encounter", "patient", "doctor", "medication")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("patient", "medication", "doctor__user")
