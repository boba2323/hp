from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.patients.models import Patient
from apps.staff.models import StaffProfile


class Ward(models.Model):
    class Type(models.TextChoices):
        GENERAL = "general", "General"
        PRIVATE = "private", "Private"
        ICU = "icu", "Intensive care"
        MATERNITY = "maternity", "Maternity"
        PEDIATRIC = "pediatric", "Pediatric"
        SURGICAL = "surgical", "Surgical"
        ISOLATION = "isolation", "Isolation"

    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=16, unique=True)
    ward_type = models.CharField(
        max_length=20, choices=Type.choices, default=Type.GENERAL
    )
    floor = models.CharField(max_length=16, blank=True)
    capacity = models.PositiveIntegerField(default=0)
    charge_per_day = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def bed_count(self) -> int:
        return self.beds.count()

    @property
    def occupied_beds(self) -> int:
        return self.beds.filter(status=Bed.Status.OCCUPIED).count()

    @property
    def available_beds(self) -> int:
        return self.beds.filter(status=Bed.Status.AVAILABLE).count()


class Bed(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        OCCUPIED = "occupied", "Occupied"
        MAINTENANCE = "maintenance", "Maintenance"
        CLEANING = "cleaning", "Cleaning"

    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name="beds")
    number = models.CharField(max_length=16)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.AVAILABLE, db_index=True
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["ward__name", "number"]
        unique_together = [("ward", "number")]

    def __str__(self) -> str:
        return f"{self.ward.code}-{self.number}"

    @property
    def current_admission(self):
        return self.admissions.filter(status=Admission.Status.ADMITTED).first()

    @property
    def current_patient(self):
        admission = self.current_admission
        return admission.patient if admission else None


class Admission(models.Model):
    class Status(models.TextChoices):
        ADMITTED = "admitted", "Admitted"
        DISCHARGED = "discharged", "Discharged"
        TRANSFERRED = "transferred", "Transferred"
        DECEASED = "deceased", "Deceased"

    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="admissions"
    )
    bed = models.ForeignKey(Bed, on_delete=models.PROTECT, related_name="admissions")
    admitting_doctor = models.ForeignKey(
        StaffProfile, on_delete=models.PROTECT, related_name="admissions"
    )
    admission_date = models.DateTimeField(default=timezone.now, db_index=True)
    discharge_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ADMITTED, db_index=True
    )
    reason = models.TextField(blank=True)
    diagnosis_summary = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    discharged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discharges",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-admission_date"]

    def __str__(self) -> str:
        return f"{self.patient.full_name} in {self.bed}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Keep the physical bed state in step with the admission record.
        if self.status == self.Status.ADMITTED:
            Bed.objects.filter(pk=self.bed_id).exclude(
                status=Bed.Status.MAINTENANCE
            ).update(status=Bed.Status.OCCUPIED)
        else:
            still_occupied = Admission.objects.filter(
                bed_id=self.bed_id, status=self.Status.ADMITTED
            ).exists()
            if not still_occupied:
                Bed.objects.filter(
                    pk=self.bed_id, status=Bed.Status.OCCUPIED
                ).update(status=Bed.Status.AVAILABLE)

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ADMITTED

    @property
    def length_of_stay_days(self) -> int:
        end = self.discharge_date or timezone.now()
        return max((end - self.admission_date).days, 0)
