from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.patients.models import Patient


class Medication(models.Model):
    class Form(models.TextChoices):
        TABLET = "tablet", "Tablet"
        CAPSULE = "capsule", "Capsule"
        SYRUP = "syrup", "Syrup"
        INJECTION = "injection", "Injection"
        CREAM = "cream", "Cream"
        DROPS = "drops", "Drops"
        INHALER = "inhaler", "Inhaler"
        SUPPOSITORY = "suppository", "Suppository"
        OTHER = "other", "Other"

    name = models.CharField(max_length=160, db_index=True)
    generic_name = models.CharField(max_length=160, blank=True)
    brand_name = models.CharField(max_length=160, blank=True)
    form = models.CharField(max_length=20, choices=Form.choices, default=Form.TABLET)
    strength = models.CharField(max_length=64, blank=True, help_text="e.g. 500mg")
    category = models.CharField(
        max_length=80, blank=True, help_text="e.g. Antibiotic, Analgesic"
    )
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    reorder_level = models.PositiveIntegerField(default=20)
    is_controlled = models.BooleanField(
        default=False, help_text="Controlled/regulated substance"
    )
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["name", "strength"])]

    def __str__(self) -> str:
        return f"{self.name} {self.strength}".strip()

    @property
    def total_stock(self) -> int:
        return (
            self.batches.filter(quantity_remaining__gt=0).aggregate(
                total=models.Sum("quantity_remaining")
            )["total"]
            or 0
        )

    @property
    def is_low_stock(self) -> bool:
        return self.total_stock <= self.reorder_level


class StockBatch(models.Model):
    medication = models.ForeignKey(
        Medication, on_delete=models.CASCADE, related_name="batches"
    )
    batch_number = models.CharField(max_length=64)
    quantity_received = models.PositiveIntegerField()
    quantity_remaining = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    supplier = models.CharField(max_length=160, blank=True)
    received_date = models.DateField(default=timezone.localdate)
    expiry_date = models.DateField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["expiry_date", "id"]
        unique_together = [("medication", "batch_number")]
        verbose_name_plural = "stock batches"

    def __str__(self) -> str:
        return f"{self.medication.name} - {self.batch_number}"

    @property
    def is_expired(self) -> bool:
        return bool(self.expiry_date and self.expiry_date < timezone.localdate())

    @property
    def is_depleted(self) -> bool:
        return self.quantity_remaining <= 0


class Dispense(models.Model):
    """Record of a prescription being handed to the patient."""

    prescription = models.OneToOneField(
        "records.Prescription", on_delete=models.PROTECT, related_name="dispense"
    )
    patient = models.ForeignKey(
        Patient, on_delete=models.PROTECT, related_name="dispenses"
    )
    batch = models.ForeignKey(
        StockBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dispenses",
    )
    quantity_dispensed = models.PositiveIntegerField()
    dispensed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="dispenses",
    )
    notes = models.TextField(blank=True)
    dispensed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-dispensed_at"]

    def __str__(self) -> str:
        return f"Dispense #{self.pk} - {self.patient.full_name}"
