from django.conf import settings
from django.db import models

from apps.patients.models import Patient
from apps.staff.models import Department, StaffProfile


class Appointment(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        CONFIRMED = "confirmed", "Confirmed"
        CHECKED_IN = "checked_in", "Checked in"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        NO_SHOW = "no_show", "No show"

    class Type(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        WALK_IN = "walk_in", "Walk in"
        FOLLOW_UP = "follow_up", "Follow up"
        EMERGENCY = "emergency", "Emergency"
        TELEMEDICINE = "telemedicine", "Telemedicine"

    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="appointments"
    )
    doctor = models.ForeignKey(
        StaffProfile, on_delete=models.PROTECT, related_name="appointments"
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointments",
    )
    scheduled_start = models.DateTimeField(db_index=True)
    scheduled_end = models.DateTimeField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SCHEDULED, db_index=True
    )
    appointment_type = models.CharField(
        max_length=20, choices=Type.choices, default=Type.SCHEDULED
    )
    reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    cancellation_reason = models.CharField(max_length=255, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_appointments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-scheduled_start"]
        indexes = [models.Index(fields=["doctor", "scheduled_start"])]

    def __str__(self) -> str:
        return f"{self.patient.full_name} with {self.doctor.full_name} @ {self.scheduled_start:%Y-%m-%d %H:%M}"

    @property
    def duration_minutes(self) -> int:
        delta = self.scheduled_end - self.scheduled_start
        return int(delta.total_seconds() // 60)

    @property
    def is_open(self) -> bool:
        return self.status in {
            self.Status.SCHEDULED,
            self.Status.CONFIRMED,
            self.Status.CHECKED_IN,
            self.Status.IN_PROGRESS,
        }
