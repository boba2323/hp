from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.codes import next_code
from apps.patients.models import Patient


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        UNPAID = "unpaid", "Unpaid"
        PARTIAL = "partial", "Partially paid"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    invoice_number = models.CharField(max_length=24, unique=True, blank=True)
    patient = models.ForeignKey(
        Patient, on_delete=models.PROTECT, related_name="invoices"
    )
    encounter = models.ForeignKey(
        "records.Encounter",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
    )
    admission = models.ForeignKey(
        "wards.Admission",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    issued_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, help_text="Percentage, e.g. 7.50"
    )
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_invoices",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "issued_date"])]

    def __str__(self) -> str:
        return f"{self.invoice_number} - {self.patient.full_name}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = next_code(Invoice, "invoice_number", "INV-")
        super().save(*args, **kwargs)

    def recalculate(self, commit: bool = True):
        """Recompute subtotal/tax/total/balance from items and payments."""
        subtotal = sum(
            (item.amount for item in self.items.all()), start=Decimal("0.00")
        )
        tax_amount = (subtotal * (self.tax_rate or 0) / Decimal("100")).quantize(
            Decimal("0.01")
        )
        total = subtotal + tax_amount - (self.discount_amount or Decimal("0.00"))
        paid = sum(
            (payment.amount for payment in self.payments.all()), start=Decimal("0.00")
        )

        self.subtotal = subtotal
        self.tax_amount = tax_amount
        self.total = max(total, Decimal("0.00"))
        self.amount_paid = paid
        self.balance = self.total - paid

        if self.status not in {self.Status.CANCELLED, self.Status.REFUNDED}:
            if paid <= 0:
                self.status = self.Status.UNPAID
            elif self.balance > 0:
                self.status = self.Status.PARTIAL
            else:
                self.status = self.Status.PAID

        if commit:
            self.save(
                update_fields=[
                    "subtotal",
                    "tax_amount",
                    "total",
                    "amount_paid",
                    "balance",
                    "status",
                    "updated_at",
                ]
            )
        return self


class InvoiceItem(models.Model):
    class Type(models.TextChoices):
        CONSULTATION = "consultation", "Consultation"
        LABORATORY = "laboratory", "Laboratory"
        PHARMACY = "pharmacy", "Pharmacy"
        BED = "bed", "Bed / ward"
        PROCEDURE = "procedure", "Procedure"
        OTHER = "other", "Other"

    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="items"
    )
    item_type = models.CharField(
        max_length=20, choices=Type.choices, default=Type.OTHER
    )
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.description} x{self.quantity}"

    def save(self, *args, **kwargs):
        self.amount = (self.quantity or 0) * (self.unit_price or 0)
        super().save(*args, **kwargs)


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        CARD = "card", "Card"
        TRANSFER = "transfer", "Bank transfer"
        INSURANCE = "insurance", "Insurance"
        MOBILE = "mobile", "Mobile money"

    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name="payments"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(
        max_length=16, choices=Method.choices, default=Method.CASH
    )
    reference = models.CharField(max_length=120, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_payments",
    )
    paid_at = models.DateTimeField(default=timezone.now, db_index=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-paid_at"]

    def __str__(self) -> str:
        return f"{self.amount} on {self.invoice.invoice_number}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.invoice.recalculate()

    def delete(self, *args, **kwargs):
        invoice = self.invoice
        result = super().delete(*args, **kwargs)
        invoice.recalculate()
        return result
