from django.contrib import admin

from apps.pharmacy.models import Dispense, Medication, StockBatch


@admin.register(Medication)
class MedicationAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "strength",
        "form",
        "category",
        "unit_price",
        "reorder_level",
        "is_controlled",
        "is_active",
    ]
    list_filter = ["form", "category", "is_controlled", "is_active"]
    search_fields = ["name", "generic_name", "brand_name", "category"]
    readonly_fields = ["created_at", "updated_at"]
    ordering = ["name"]


@admin.register(StockBatch)
class StockBatchAdmin(admin.ModelAdmin):
    list_display = [
        "batch_number",
        "medication",
        "quantity_received",
        "quantity_remaining",
        "expiry_date",
        "supplier",
    ]
    list_filter = ["expiry_date", "received_date", "supplier"]
    search_fields = ["batch_number", "medication__name", "supplier"]
    autocomplete_fields = ["medication"]
    readonly_fields = ["created_at"]
    date_hierarchy = "expiry_date"


@admin.register(Dispense)
class DispenseAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "patient",
        "prescription",
        "batch",
        "quantity_dispensed",
        "dispensed_by",
        "dispensed_at",
    ]
    list_filter = ["dispensed_at", "dispensed_by"]
    search_fields = [
        "patient__first_name",
        "patient__last_name",
        "patient__mrn",
        "prescription__medication__name",
    ]
    autocomplete_fields = ["prescription", "patient", "batch", "dispensed_by"]
    readonly_fields = ["dispensed_at"]
    date_hierarchy = "dispensed_at"
