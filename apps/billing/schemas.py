from datetime import date, datetime
from decimal import Decimal

from ninja import ModelSchema, Schema

from apps.billing.models import Invoice, InvoiceItem, Payment


class PatientBriefOut(Schema):
    id: int
    mrn: str
    full_name: str
    age: int | None = None
    gender: str = ""


class UserBriefOut(Schema):
    id: int
    full_name: str


class InvoiceItemOut(ModelSchema):
    class Meta:
        model = InvoiceItem
        fields = ["id", "item_type", "description", "quantity", "unit_price", "amount"]


class InvoiceItemIn(Schema):
    item_type: str = "other"
    description: str
    quantity: Decimal = Decimal("1.00")
    unit_price: Decimal = Decimal("0.00")


class InvoiceItemUpdateIn(Schema):
    item_type: str | None = None
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None


class PaymentInvoiceBriefOut(ModelSchema):
    class Meta:
        model = Invoice
        fields = ["id", "invoice_number", "total", "balance"]


class PaymentOut(ModelSchema):
    invoice: PaymentInvoiceBriefOut
    received_by: UserBriefOut | None = None

    class Meta:
        model = Payment
        fields = ["id", "amount", "method", "reference", "paid_at", "notes"]


class InvoiceOut(ModelSchema):
    patient: PatientBriefOut

    class Meta:
        model = Invoice
        fields = [
            "id",
            "invoice_number",
            "status",
            "issued_date",
            "due_date",
            "subtotal",
            "tax_rate",
            "tax_amount",
            "discount_amount",
            "total",
            "amount_paid",
            "balance",
            "notes",
            "created_at",
        ]


class InvoiceDetailOut(InvoiceOut):
    items: list[InvoiceItemOut] = []
    payments: list[PaymentOut] = []


class InvoiceCreateIn(Schema):
    patient: int
    encounter: int | None = None
    admission: int | None = None
    due_date: date | None = None
    tax_rate: Decimal | None = None
    discount_amount: Decimal | None = None
    notes: str = ""
    items: list[InvoiceItemIn] = []


class InvoiceUpdateIn(Schema):
    due_date: date | None = None
    tax_rate: Decimal | None = None
    discount_amount: Decimal | None = None
    notes: str | None = None
    status: str | None = None


class PaymentIn(Schema):
    amount: Decimal
    method: str = "cash"
    reference: str = ""
    notes: str = ""
    paid_at: datetime | None = None
