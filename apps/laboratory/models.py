from django.db import models
from django.utils import timezone

from apps.patients.models import Patient
from apps.staff.models import StaffProfile


class LabTest(models.Model):
    class Category(models.TextChoices):
        HEMATOLOGY = "hematology", "Hematology"
        CHEMISTRY = "chemistry", "Clinical chemistry"
        MICROBIOLOGY = "microbiology", "Microbiology"
        URINALYSIS = "urinalysis", "Urinalysis"
        IMAGING = "imaging", "Imaging"
        PATHOLOGY = "pathology", "Pathology"
        OTHER = "other", "Other"

    name = models.CharField(max_length=160, unique=True)
    code = models.CharField(max_length=32, unique=True)
    category = models.CharField(
        max_length=20, choices=Category.choices, default=Category.OTHER
    )
    sample_type = models.CharField(max_length=64, blank=True, help_text="e.g. Blood")
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    turnaround_hours = models.PositiveIntegerField(default=24)
    normal_range = models.CharField(max_length=120, blank=True)
    unit = models.CharField(max_length=32, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class LabOrder(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COLLECTED = "collected", "Sample collected"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class Priority(models.TextChoices):
        ROUTINE = "routine", "Routine"
        URGENT = "urgent", "Urgent"
        STAT = "stat", "STAT"

    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="lab_orders"
    )
    ordered_by = models.ForeignKey(
        StaffProfile, on_delete=models.PROTECT, related_name="lab_orders"
    )
    encounter = models.ForeignKey(
        "records.Encounter",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lab_orders",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    priority = models.CharField(
        max_length=16, choices=Priority.choices, default=Priority.ROUTINE
    )
    ordered_at = models.DateTimeField(default=timezone.now, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-ordered_at"]

    def __str__(self) -> str:
        return f"Lab order #{self.pk} - {self.patient.full_name}"

    @property
    def total(self):
        return sum((item.price for item in self.items.all()), start=0)

    @property
    def has_results(self) -> bool:
        return self.items.exclude(result_value="").exists()


class LabOrderItem(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    order = models.ForeignKey(
        LabOrder, on_delete=models.CASCADE, related_name="items"
    )
    test = models.ForeignKey(
        LabTest, on_delete=models.PROTECT, related_name="order_items"
    )
    price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, help_text="Price at time of order"
    )
    result_value = models.CharField(max_length=120, blank=True)
    result_unit = models.CharField(max_length=32, blank=True)
    is_abnormal = models.BooleanField(default=False)
    remarks = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.test.name} for order #{self.order_id}"

    def save(self, *args, **kwargs):
        # Snapshot the catalogue price on first save so later price changes
        # never rewrite historical orders.
        if self._state.adding and self.test_id and not self.price:
            self.price = self.test.price
        if self.result_value and self.status == self.Status.PENDING:
            self.status = self.Status.COMPLETED
            self.completed_at = self.completed_at or timezone.now()
        super().save(*args, **kwargs)
