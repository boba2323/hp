from django.conf import settings
from django.db import models

from apps.appointments.models import Appointment
from apps.patients.models import Patient
from apps.staff.models import StaffProfile


class Encounter(models.Model):
    """A single clinical contact - the anchor for diagnoses and prescriptions."""

    class Type(models.TextChoices):
        OUTPATIENT = "outpatient", "Outpatient"
        INPATIENT = "inpatient", "Inpatient"
        EMERGENCY = "emergency", "Emergency"
        FOLLOW_UP = "follow_up", "Follow up"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="encounters"
    )
    doctor = models.ForeignKey(
        StaffProfile, on_delete=models.PROTECT, related_name="encounters"
    )
    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="encounter",
    )
    encounter_type = models.CharField(
        max_length=20, choices=Type.choices, default=Type.OUTPATIENT, db_index=True
    )
    encounter_date = models.DateTimeField(db_index=True)
    chief_complaint = models.TextField(blank=True)
    history_of_present_illness = models.TextField(blank=True)
    examination_notes = models.TextField(blank=True)
    treatment_plan = models.TextField(blank=True)
    follow_up_date = models.DateField(null=True, blank=True)

    # Vitals
    temperature_c = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True
    )
    bp_systolic = models.PositiveIntegerField(null=True, blank=True)
    bp_diastolic = models.PositiveIntegerField(null=True, blank=True)
    pulse = models.PositiveIntegerField(null=True, blank=True, help_text="bpm")
    respiratory_rate = models.PositiveIntegerField(null=True, blank=True)
    spo2 = models.PositiveIntegerField(null=True, blank=True, help_text="%")
    weight_kg = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    height_cm = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )

    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.OPEN, db_index=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_encounters",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-encounter_date"]
        verbose_name = "encounter"
        verbose_name_plural = "encounters"

    def __str__(self) -> str:
        return f"Encounter #{self.pk} - {self.patient.full_name}"

    @property
    def blood_pressure(self) -> str | None:
        if self.bp_systolic and self.bp_diastolic:
            return f"{self.bp_systolic}/{self.bp_diastolic}"
        return None

    @property
    def bmi(self) -> float | None:
        if self.weight_kg and self.height_cm:
            height_m = float(self.height_cm) / 100
            if height_m > 0:
                return round(float(self.weight_kg) / (height_m**2), 1)
        return None


class Diagnosis(models.Model):
    class Type(models.TextChoices):
        PRIMARY = "primary", "Primary"
        SECONDARY = "secondary", "Secondary"
        DIFFERENTIAL = "differential", "Differential"

    encounter = models.ForeignKey(
        Encounter, on_delete=models.CASCADE, related_name="diagnoses"
    )
    code = models.CharField(max_length=16, blank=True, help_text="ICD-10 code")
    description = models.CharField(max_length=255)
    diagnosis_type = models.CharField(
        max_length=16, choices=Type.choices, default=Type.PRIMARY
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["diagnosis_type", "id"]

    def __str__(self) -> str:
        return f"{self.code} {self.description}".strip()


class Prescription(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        DISPENSED = "dispensed", "Dispensed"
        PARTIAL = "partial", "Partially dispensed"
        CANCELLED = "cancelled", "Cancelled"

    encounter = models.ForeignKey(
        Encounter, on_delete=models.CASCADE, related_name="prescriptions"
    )
    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="prescriptions"
    )
    doctor = models.ForeignKey(
        StaffProfile, on_delete=models.PROTECT, related_name="prescriptions"
    )
    medication = models.ForeignKey(
        "pharmacy.Medication", on_delete=models.PROTECT, related_name="prescriptions"
    )
    dosage = models.CharField(max_length=80, help_text="e.g. 500mg")
    frequency = models.CharField(max_length=80, help_text="e.g. twice daily")
    route = models.CharField(max_length=40, default="oral")
    duration_days = models.PositiveIntegerField(default=1)
    quantity = models.PositiveIntegerField(default=1)
    instructions = models.TextField(blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.medication.name} for {self.patient.full_name}"
