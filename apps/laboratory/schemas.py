from decimal import Decimal
from typing import Literal

from ninja import ModelSchema, Schema

from apps.laboratory.models import LabOrder, LabOrderItem, LabTest


class PatientBriefOut(Schema):
    id: int
    mrn: str
    full_name: str
    age: int | None = None
    gender: str = ""


class StaffBriefOut(Schema):
    id: int
    full_name: str


class LabTestOut(ModelSchema):
    class Meta:
        model = LabTest
        fields = [
            "id",
            "name",
            "code",
            "category",
            "sample_type",
            "price",
            "turnaround_hours",
            "normal_range",
            "unit",
            "description",
            "is_active",
        ]


class LabTestIn(Schema):
    name: str
    code: str
    category: str = "other"
    sample_type: str = ""
    price: Decimal = Decimal("0.00")
    turnaround_hours: int = 24
    normal_range: str = ""
    unit: str = ""
    description: str = ""
    is_active: bool = True


class LabTestUpdateIn(Schema):
    name: str | None = None
    code: str | None = None
    category: str | None = None
    sample_type: str | None = None
    price: Decimal | None = None
    turnaround_hours: int | None = None
    normal_range: str | None = None
    unit: str | None = None
    description: str | None = None
    is_active: bool | None = None


class LabTestBriefOut(ModelSchema):
    class Meta:
        model = LabTest
        fields = ["id", "name", "code", "category", "unit", "normal_range", "price"]


class LabOrderItemOut(ModelSchema):
    test: LabTestBriefOut

    class Meta:
        model = LabOrderItem
        fields = [
            "id",
            "price",
            "result_value",
            "result_unit",
            "is_abnormal",
            "remarks",
            "status",
            "completed_at",
        ]


class LabOrderOut(ModelSchema):
    patient: PatientBriefOut
    ordered_by: StaffBriefOut
    total: Decimal
    has_results: bool

    class Meta:
        model = LabOrder
        fields = [
            "id",
            "status",
            "priority",
            "ordered_at",
            "completed_at",
            "notes",
            "created_at",
        ]


class LabOrderDetailOut(LabOrderOut):
    items: list[LabOrderItemOut] = []


class LabOrderCreateIn(Schema):
    patient: int
    ordered_by: int | None = None
    encounter: int | None = None
    priority: Literal["routine", "urgent", "stat"] = "routine"
    notes: str = ""
    test_ids: list[int] = []


class LabOrderUpdateIn(Schema):
    priority: Literal["routine", "urgent", "stat"] | None = None
    notes: str | None = None


class LabOrderItemResultIn(Schema):
    """One result line - only the fields actually supplied are written."""

    item: int
    result_value: str
    result_unit: str | None = None
    is_abnormal: bool | None = None
    remarks: str | None = None
