from django.contrib import admin

from apps.billing.models import Invoice, InvoiceItem, Payment


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    fields = ("item_type", "description", "quantity", "unit_price", "amount")
    readonly_fields = ("amount",)


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    fields = ("amount", "method", "reference", "received_by", "paid_at", "notes")
    autocomplete_fields = ("received_by",)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_number",
        "patient",
        "status",
        "issued_date",
        "due_date",
        "total",
        "amount_paid",
        "balance",
    )
    list_filter = ("status", "issued_date", "due_date")
    search_fields = (
        "invoice_number",
        "patient__first_name",
        "patient__last_name",
        "patient__mrn",
    )
    autocomplete_fields = ("patient", "encounter", "admission", "created_by")
    inlines = [InvoiceItemInline, PaymentInline]
    date_hierarchy = "issued_date"
    readonly_fields = (
        "subtotal",
        "tax_amount",
        "total",
        "amount_paid",
        "balance",
        "created_at",
        "updated_at",
    )


@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):
    list_display = ("id", "invoice", "item_type", "description", "quantity", "amount")
    list_filter = ("item_type",)
    search_fields = ("description", "invoice__invoice_number", "invoice__patient__mrn")
    autocomplete_fields = ("invoice",)
    list_select_related = ("invoice",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "invoice",
        "amount",
        "method",
        "reference",
        "received_by",
        "paid_at",
    )
    list_filter = ("method", "paid_at")
    search_fields = ("reference", "invoice__invoice_number", "invoice__patient__mrn")
    autocomplete_fields = ("invoice", "received_by")
    date_hierarchy = "paid_at"
    list_select_related = ("invoice", "received_by")
