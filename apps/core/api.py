"""Cross-cutting endpoints: health, dashboard roll-up and enum lookups."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone
from ninja import Router, Schema

from apps.accounts.auth import jwt_auth
from apps.accounts.models import User
from apps.appointments.models import Appointment
from apps.billing.models import Invoice, InvoiceItem
from apps.core.utils import current_user
from apps.laboratory.models import LabOrder
from apps.patients.models import Patient
from apps.pharmacy.models import Medication, StockBatch
from apps.wards.models import Admission, Bed

router = Router(tags=["core"])


class HealthOut(Schema):
    status: str
    version: str
    time: str


class DashboardOut(Schema):
    patients_total: int
    patients_active: int
    patients_new_this_month: int
    appointments_today: int
    appointments_upcoming: int
    appointments_completed_today: int
    current_inpatients: int
    beds_total: int
    beds_available: int
    lab_orders_pending: int
    low_stock_medications: int
    expiring_batches: int
    revenue_this_month: Decimal
    outstanding_balance: Decimal
    staff_total: int


@router.get("/health", response=HealthOut, auth=None)
def health(request):
    return {
        "status": "ok",
        "version": "1.0.0",
        "time": timezone.now().isoformat(),
    }


@router.get("/dashboard", response=DashboardOut, auth=jwt_auth)
def dashboard(request):
    """Single roll-up call so the React dashboard needs one round trip."""
    current_user(request)

    today = timezone.localdate()
    now = timezone.now()
    month_start = today.replace(day=1)

    open_statuses = [
        Appointment.Status.SCHEDULED,
        Appointment.Status.CONFIRMED,
        Appointment.Status.CHECKED_IN,
        Appointment.Status.IN_PROGRESS,
    ]

    todays_appointments = Appointment.objects.filter(
        scheduled_start__date=today
    ).exclude(status=Appointment.Status.CANCELLED)

    low_stock = sum(
        1
        for medication in Medication.objects.filter(is_active=True).annotate(
            stock=Sum("batches__quantity_remaining")
        )
        if (medication.stock or 0) <= medication.reorder_level
    )

    invoices_this_month = Invoice.objects.filter(
        issued_date__gte=month_start
    ).exclude(status__in=[Invoice.Status.CANCELLED, Invoice.Status.REFUNDED])

    return {
        "patients_total": Patient.objects.count(),
        "patients_active": Patient.objects.filter(is_active=True).count(),
        "patients_new_this_month": Patient.objects.filter(
            created_at__date__gte=month_start
        ).count(),
        "appointments_today": todays_appointments.count(),
        "appointments_upcoming": Appointment.objects.filter(
            status__in=open_statuses, scheduled_start__gte=now
        ).count(),
        "appointments_completed_today": Appointment.objects.filter(
            status=Appointment.Status.COMPLETED, scheduled_start__date=today
        ).count(),
        "current_inpatients": Admission.objects.filter(
            status=Admission.Status.ADMITTED
        ).count(),
        "beds_total": Bed.objects.count(),
        "beds_available": Bed.objects.filter(status=Bed.Status.AVAILABLE).count(),
        "lab_orders_pending": LabOrder.objects.exclude(
            status__in=[LabOrder.Status.COMPLETED, LabOrder.Status.CANCELLED]
        ).count(),
        "low_stock_medications": low_stock,
        "expiring_batches": StockBatch.objects.filter(
            quantity_remaining__gt=0,
            expiry_date__isnull=False,
            expiry_date__lte=today + timedelta(days=90),
            expiry_date__gte=today,
        ).count(),
        "revenue_this_month": invoices_this_month.aggregate(
            total=Sum("amount_paid")
        )["total"]
        or Decimal("0.00"),
        "outstanding_balance": Invoice.objects.filter(balance__gt=0).aggregate(
            total=Sum("balance")
        )["total"]
        or Decimal("0.00"),
        "staff_total": User.objects.filter(is_active=True).count(),
    }


@router.get("/enums", auth=jwt_auth)
def enums(request):
    """Every model choice list, so the frontend never hardcodes a status string."""
    current_user(request)

    def choices(choice_class):
        return [{"value": value, "label": label} for value, label in choice_class.choices]

    return {
        "user_role": choices(User.Role),
        "gender": choices(Patient.Gender),
        "blood_group": choices(Patient.BloodGroup),
        "marital_status": choices(Patient.MaritalStatus),
        "appointment_status": choices(Appointment.Status),
        "appointment_type": choices(Appointment.Type),
        "invoice_status": choices(Invoice.Status),
        "invoice_item_type": choices(InvoiceItem.Type),
        "lab_order_status": choices(LabOrder.Status),
        "lab_order_priority": choices(LabOrder.Priority),
        "bed_status": choices(Bed.Status),
        "admission_status": choices(Admission.Status),
    }


@router.get("/appointments-by-status", auth=jwt_auth)
def appointments_by_status(request, days: int = 30):
    """Small aggregate used by the dashboard chart."""
    current_user(request)
    since = timezone.localdate() - timedelta(days=max(1, min(days, 365)))
    rows = (
        Appointment.objects.filter(scheduled_start__date__gte=since)
        .values("status")
        .annotate(count=Count("id"))
        .order_by("status")
    )
    return {"since": since.isoformat(), "results": list(rows)}


@router.get("/bed-occupancy-by-ward", auth=jwt_auth)
def bed_occupancy_by_ward(request):
    current_user(request)
    rows = (
        Bed.objects.values("ward__name", "ward__code")
        .annotate(
            total=Count("id"),
            occupied=Count("id", filter=Q(status=Bed.Status.OCCUPIED)),
            available=Count("id", filter=Q(status=Bed.Status.AVAILABLE)),
        )
        .order_by("ward__name")
    )
    return {"results": list(rows)}
