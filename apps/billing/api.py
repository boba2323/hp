"""Billing API - invoices, line items, payments and the revenue summary.

Every money value is a :class:`decimal.Decimal`; the arithmetic itself lives in
``Invoice.recalculate()`` so there is exactly one place that decides what an
invoice's subtotal, tax, total, paid amount, balance and status are.
"""

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from ninja import Router
from ninja.errors import HttpError

from apps.accounts.auth import jwt_auth
from apps.accounts.models import User
from apps.billing.models import Invoice, InvoiceItem, Payment
from apps.billing.schemas import (
    InvoiceCreateIn,
    InvoiceDetailOut,
    InvoiceItemIn,
    InvoiceItemOut,
    InvoiceItemUpdateIn,
    InvoiceOut,
    InvoiceUpdateIn,
    PaymentIn,
    PaymentOut,
)
from apps.core.pagination import apply_ordering, apply_search, paginate
from apps.core.schemas import MessageOut, Page
from apps.core.utils import (
    current_user,
    drop_nullable_nulls,
    get_object_or_404,
    require_roles,
)
from apps.patients.models import Patient
from apps.records.models import Encounter
from apps.wards.models import Admission

router = Router(tags=["billing"])

ORDERING_FIELDS = ["invoice_number", "issued_date", "total", "balance", "created_at"]
SEARCH_FIELDS = [
    "invoice_number",
    "patient__first_name",
    "patient__last_name",
    "patient__mrn",
]
PAYMENT_ORDERING_FIELDS = ["paid_at", "amount", "method"]
LOCKED_STATUSES = {Invoice.Status.CANCELLED, Invoice.Status.REFUNDED}
MANUAL_STATUSES = {Invoice.Status.CANCELLED, Invoice.Status.REFUNDED}
ZERO = Decimal("0.00")


# --- helpers ----------------------------------------------------------------


def _get_invoice(invoice_id: int) -> Invoice:
    """Invoice with everything the nested serializers need, no N+1."""
    invoice = (
        Invoice.objects.select_related("patient")
        .prefetch_related("items", "payments__received_by", "payments__invoice")
        .filter(pk=invoice_id)
        .first()
    )
    if invoice is None:
        raise HttpError(404, "Invoice not found")
    return invoice


def _assert_editable(invoice: Invoice) -> None:
    """Line items of a cancelled/refunded invoice are frozen."""
    if invoice.status in LOCKED_STATUSES:
        raise HttpError(
            400,
            f"Cannot modify a {invoice.get_status_display().lower()} invoice",
        )


def _money(value) -> Decimal:
    """Render a money figure with two decimal places whatever the backend did
    with the aggregate's scale (SQLite hands back ``Decimal('100')`` for what
    is a two-decimal column)."""
    return Decimal(value or ZERO).quantize(Decimal("0.01"))


def _parse_bound(raw: str | None, label: str) -> date | None:
    if not raw:
        return None
    parsed = parse_date(raw)
    if parsed is None:
        moment = parse_datetime(raw)
        parsed = moment.date() if moment else None
    if parsed is None:
        raise HttpError(400, f"{label} must be an ISO date (YYYY-MM-DD)")
    return parsed


# --- invoices ---------------------------------------------------------------


@router.get("/summary/", response=dict, auth=jwt_auth)
def billing_summary(request):
    """Revenue dashboard.

    Cancelled and refunded invoices are left out of every money figure - the
    cash they may once have carried is not revenue - but they still appear in
    ``counts_by_status``.
    """
    billable = Invoice.objects.exclude(status__in=list(LOCKED_STATUSES))
    money = billable.aggregate(
        total_invoiced=Sum("total", default=ZERO),
        total_collected=Sum("amount_paid", default=ZERO),
        total_outstanding=Sum("balance", default=ZERO),
    )

    counts_by_status = {value: 0 for value, _ in Invoice.Status.choices}
    for row in Invoice.objects.values("status").annotate(count=Count("id")):
        counts_by_status[row["status"]] = row["count"]

    month_start = timezone.localdate().replace(day=1)
    collections = (
        Payment.objects.filter(paid_at__date__gte=month_start)
        .exclude(invoice__status__in=list(LOCKED_STATUSES))
        .aggregate(total=Sum("amount", default=ZERO))["total"]
    )

    return {
        "total_invoiced": _money(money["total_invoiced"]),
        "total_collected": _money(money["total_collected"]),
        "total_outstanding": _money(money["total_outstanding"]),
        "counts_by_status": counts_by_status,
        "collections_this_month": _money(collections),
        "month": month_start.strftime("%Y-%m"),
    }


@router.get("/invoices/", response=Page[InvoiceOut], auth=jwt_auth)
def list_invoices(
    request,
    status: str | None = None,
    patient: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    unpaid: bool | None = None,
    search: str | None = None,
):
    queryset = Invoice.objects.select_related("patient")

    if status:
        queryset = queryset.filter(status=status)
    if patient:
        queryset = queryset.filter(patient_id=patient)
    if unpaid:
        queryset = queryset.filter(balance__gt=ZERO)

    start = _parse_bound(date_from, "date_from")
    end = _parse_bound(date_to, "date_to")
    if start:
        queryset = queryset.filter(issued_date__gte=start)
    if end:
        queryset = queryset.filter(issued_date__lte=end)

    queryset = apply_search(queryset, request, SEARCH_FIELDS)
    queryset = apply_ordering(queryset, request, ORDERING_FIELDS, "-created_at")
    return paginate(request, queryset, InvoiceOut)


@router.post("/invoices/", response={201: InvoiceDetailOut}, auth=jwt_auth)
def create_invoice(request, payload: InvoiceCreateIn):
    """Create an invoice and its line items in one transaction.

    ``recalculate()`` derives subtotal/tax/total/balance and, once payments
    exist, the status. With no payments recorded the invoice settles on
    ``unpaid`` (an invoice that never gets an item keeps its ``draft`` status).
    """
    patient = get_object_or_404(Patient, pk=payload.patient)
    encounter = (
        get_object_or_404(Encounter, pk=payload.encounter) if payload.encounter else None
    )
    admission = (
        get_object_or_404(Admission, pk=payload.admission) if payload.admission else None
    )

    with transaction.atomic():
        invoice = Invoice.objects.create(
            patient=patient,
            encounter=encounter,
            admission=admission,
            due_date=payload.due_date,
            tax_rate=payload.tax_rate or ZERO,
            discount_amount=payload.discount_amount or ZERO,
            notes=payload.notes,
            created_by=current_user(request),
        )
        for item in payload.items:
            InvoiceItem.objects.create(invoice=invoice, **item.model_dump())
        invoice.recalculate()

    return 201, _get_invoice(invoice.pk)


@router.get("/invoices/{int:invoice_id}", response=InvoiceDetailOut, auth=jwt_auth)
def get_invoice(request, invoice_id: int):
    return _get_invoice(invoice_id)


@router.patch("/invoices/{int:invoice_id}", response=InvoiceDetailOut, auth=jwt_auth)
def update_invoice(request, invoice_id: int, payload: InvoiceUpdateIn):
    """Update the invoice header.

    ``status`` is derived from the payments on the invoice, so only the two
    terminal states a human decides - ``cancelled`` and ``refunded`` - may be
    set by hand. Everything else is rejected.
    """
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    data = drop_nullable_nulls(Invoice, payload.model_dump(exclude_unset=True))

    new_status = data.pop("status", None)
    if new_status is not None:
        if new_status not in MANUAL_STATUSES:
            raise HttpError(400, "Status is derived from payments")
        invoice.status = new_status

    for field, value in data.items():
        if value is None and field in {"tax_rate", "discount_amount"}:
            continue
        setattr(invoice, field, value)
    invoice.save()

    # recalculate() never touches a cancelled/refunded status.
    invoice.recalculate()
    return _get_invoice(invoice_id)


@router.delete("/invoices/{int:invoice_id}", response=MessageOut, auth=jwt_auth)
def delete_invoice(request, invoice_id: int):
    """Delete an invoice that has never been paid.

    Once money has changed hands the invoice is a financial record: cancel it
    instead (``PATCH /invoices/{id}`` with ``{"status": "cancelled"}``).
    """
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    if invoice.payments.exists():
        raise HttpError(
            400, "Cannot delete an invoice with payments — cancel it instead"
        )

    number = invoice.invoice_number
    invoice.delete()
    return {"detail": f"Invoice {number} deleted"}


# --- invoice items ----------------------------------------------------------


@router.post("/invoices/{int:invoice_id}/items", response={201: InvoiceItemOut}, auth=jwt_auth)
def add_invoice_item(request, invoice_id: int, payload: InvoiceItemIn):
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    _assert_editable(invoice)

    item = InvoiceItem.objects.create(invoice=invoice, **payload.model_dump())
    invoice.recalculate()
    return 201, item


@router.patch("/items/{int:item_id}", response=InvoiceItemOut, auth=jwt_auth)
def update_invoice_item(request, item_id: int, payload: InvoiceItemUpdateIn):
    item = get_object_or_404(InvoiceItem, pk=item_id)
    _assert_editable(item.invoice)

    for field, value in drop_nullable_nulls(
        InvoiceItem, payload.model_dump(exclude_unset=True)
    ).items():
        setattr(item, field, value)
    item.save()  # recomputes amount = quantity * unit_price
    item.invoice.recalculate()
    return item


@router.delete("/items/{int:item_id}", response=MessageOut, auth=jwt_auth)
def delete_invoice_item(request, item_id: int):
    item = get_object_or_404(InvoiceItem, pk=item_id)
    invoice = item.invoice
    _assert_editable(invoice)

    item.delete()
    invoice.recalculate()
    return {"detail": "Invoice item removed"}


# --- payments ---------------------------------------------------------------


@router.get("/payments", response=Page[PaymentOut], auth=jwt_auth)
def list_payments(
    request,
    method: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    patient: int | None = None,
    invoice: int | None = None,
):
    queryset = Payment.objects.select_related("invoice", "received_by")

    if method:
        queryset = queryset.filter(method=method)
    if patient:
        queryset = queryset.filter(invoice__patient_id=patient)
    if invoice:
        queryset = queryset.filter(invoice_id=invoice)

    start = _parse_bound(date_from, "date_from")
    end = _parse_bound(date_to, "date_to")
    if start:
        queryset = queryset.filter(paid_at__date__gte=start)
    if end:
        queryset = queryset.filter(paid_at__date__lte=end)

    queryset = apply_ordering(queryset, request, PAYMENT_ORDERING_FIELDS, "-paid_at")
    return paginate(request, queryset, PaymentOut)


@router.post(
    "/invoices/{int:invoice_id}/payments", response={201: PaymentOut}, auth=jwt_auth
)
def record_payment(request, invoice_id: int, payload: PaymentIn):
    """Record a payment against an invoice.

    Recording money is a cashier action, so it is limited to administrators,
    accountants and receptionists.
    """
    actor = require_roles(
        request, User.Role.ADMIN, User.Role.ACCOUNTANT, User.Role.RECEPTIONIST
    )
    invoice = get_object_or_404(Invoice, pk=invoice_id)

    if invoice.status in LOCKED_STATUSES:
        raise HttpError(
            400, f"Cannot record a payment against a {invoice.status} invoice"
        )
    if payload.amount <= 0:
        raise HttpError(400, "Payment amount must be greater than zero")
    if payload.amount > invoice.balance:
        raise HttpError(
            400, f"Payment exceeds the outstanding balance of {invoice.balance}"
        )

    data = payload.model_dump(exclude_unset=True)
    data.pop("amount", None)
    if data.get("paid_at") is None:
        data.pop("paid_at", None)

    # Payment.save() recalculates the invoice; we call it again explicitly so
    # the returned invoice figures are never in doubt.
    payment = Payment.objects.create(
        invoice=invoice, amount=payload.amount, received_by=actor, **data
    )
    invoice.recalculate()
    return 201, payment


@router.get("/invoices/{int:invoice_id}/payments", response=Page[PaymentOut], auth=jwt_auth)
def list_invoice_payments(request, invoice_id: int):
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    queryset = (
        Payment.objects.select_related("invoice", "received_by")
        .filter(invoice_id=invoice.pk)
        .order_by("-paid_at")
    )
    return paginate(request, queryset, PaymentOut)


@router.delete("/payments/{int:payment_id}", response=MessageOut, auth=jwt_auth)
def delete_payment(request, payment_id: int):
    """Reverse a payment. Administrators only - ``Payment.delete()``
    recalculates the invoice it was taken against."""
    require_roles(request, User.Role.ADMIN)
    payment = get_object_or_404(Payment, pk=payment_id)
    invoice_number = payment.invoice.invoice_number

    payment.delete()
    return {"detail": f"Payment reversed on invoice {invoice_number}"}
