"""Schemas for the pharmacy app - formulary, stock batches and dispensing.

Nested patient/doctor shapes are declared locally rather than imported from
``apps.patients.schemas`` / ``apps.staff.schemas`` so the pharmacy API only
depends on the models it actually reads.
"""

from datetime import date

from ninja import ModelSchema, Schema

from apps.pharmacy.models import Dispense, Medication, StockBatch
from apps.records.models import Prescription

# --- Nested shapes ----------------------------------------------------------


class PatientBrief(Schema):
    id: int
    mrn: str
    full_name: str


class StaffBrief(Schema):
    id: int
    full_name: str


class MedicationBrief(Schema):
    id: int
    name: str
    strength: str = ""
    form: str


# --- Medications ------------------------------------------------------------


class MedicationOut(ModelSchema):
    """Every medication column plus the two computed stock helpers."""

    total_stock: int
    is_low_stock: bool

    class Meta:
        model = Medication
        fields = "__all__"


class MedicationIn(ModelSchema):
    class Meta:
        model = Medication
        fields = [
            "name",
            "generic_name",
            "brand_name",
            "form",
            "strength",
            "category",
            "unit_price",
            "cost_price",
            "reorder_level",
            "is_controlled",
            "is_active",
            "description",
        ]
        fields_optional = [
            "generic_name",
            "brand_name",
            "strength",
            "category",
            "unit_price",
            "cost_price",
            "reorder_level",
            "is_controlled",
            "is_active",
            "description",
        ]


class MedicationUpdateIn(ModelSchema):
    """PATCH body - every field optional, omitted fields are left untouched."""

    class Meta:
        model = Medication
        fields = [
            "name",
            "generic_name",
            "brand_name",
            "form",
            "strength",
            "category",
            "unit_price",
            "cost_price",
            "reorder_level",
            "is_controlled",
            "is_active",
            "description",
        ]
        fields_optional = "__all__"


# --- Stock batches ----------------------------------------------------------


class BatchOut(ModelSchema):
    medication: MedicationBrief
    is_expired: bool
    is_depleted: bool

    class Meta:
        model = StockBatch
        fields = [
            "id",
            "batch_number",
            "quantity_received",
            "quantity_remaining",
            "unit_cost",
            "supplier",
            "received_date",
            "expiry_date",
            "created_at",
        ]


class BatchIn(ModelSchema):
    class Meta:
        model = StockBatch
        fields = [
            "batch_number",
            "quantity_received",
            "quantity_remaining",
            "unit_cost",
            "supplier",
            "received_date",
            "expiry_date",
        ]
        fields_optional = [
            "quantity_remaining",
            "unit_cost",
            "supplier",
            "received_date",
            "expiry_date",
        ]


class BatchUpdateIn(ModelSchema):
    class Meta:
        model = StockBatch
        fields = [
            "batch_number",
            "quantity_received",
            "quantity_remaining",
            "unit_cost",
            "supplier",
            "received_date",
            "expiry_date",
        ]
        fields_optional = "__all__"


class BatchBrief(Schema):
    id: int
    batch_number: str
    expiry_date: date | None = None


class StockOut(Schema):
    """Answer for ``GET /medications/{id}/stock``."""

    medication: MedicationBrief
    total_stock: int
    reorder_level: int
    is_low_stock: bool
    batches: list[BatchOut]


# --- Dispensing -------------------------------------------------------------


class PrescriptionBrief(Schema):
    id: int
    status: str
    dosage: str
    frequency: str
    quantity: int
    medication: MedicationBrief


class PendingPrescriptionOut(ModelSchema):
    """A row of the pharmacist's work queue - patient, drug and prescriber."""

    patient: PatientBrief
    medication: MedicationBrief
    doctor: StaffBrief

    class Meta:
        model = Prescription
        fields = [
            "id",
            "dosage",
            "frequency",
            "route",
            "duration_days",
            "quantity",
            "instructions",
            "status",
            "created_at",
        ]


class DispenseIn(Schema):
    prescription: int
    batch: int | None = None
    quantity_dispensed: int | None = None
    notes: str = ""


class DispenseOut(ModelSchema):
    prescription: PrescriptionBrief
    patient: PatientBrief
    batch: BatchBrief | None = None
    dispensed_by: StaffBrief | None = None

    class Meta:
        model = Dispense
        fields = ["id", "quantity_dispensed", "notes", "dispensed_at"]
