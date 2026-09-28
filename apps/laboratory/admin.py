from django.contrib import admin

from apps.laboratory.models import LabOrder, LabOrderItem, LabTest


@admin.register(LabTest)
class LabTestAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "category",
        "sample_type",
        "price",
        "turnaround_hours",
        "is_active",
    )
    list_filter = ("category", "is_active", "sample_type")
    search_fields = ("name", "code", "sample_type", "description")
    ordering = ("name",)
    list_per_page = 50


class LabOrderItemInline(admin.TabularInline):
    model = LabOrderItem
    extra = 0
    autocomplete_fields = ("test",)
    fields = (
        "test",
        "price",
        "result_value",
        "result_unit",
        "is_abnormal",
        "remarks",
        "status",
        "completed_at",
    )
    readonly_fields = ("completed_at",)


@admin.register(LabOrder)
class LabOrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "patient",
        "status",
        "priority",
        "ordered_at",
        "completed_at",
        "ordered_by",
    )
    list_filter = ("status", "priority", "ordered_at")
    search_fields = (
        "patient__first_name",
        "patient__last_name",
        "patient__mrn",
        "items__test__name",
        "notes",
    )
    autocomplete_fields = ("patient", "ordered_by", "encounter")
    inlines = [LabOrderItemInline]
    date_hierarchy = "ordered_at"
    readonly_fields = ("created_at", "updated_at")


@admin.register(LabOrderItem)
class LabOrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "test",
        "status",
        "result_value",
        "is_abnormal",
        "completed_at",
    )
    list_filter = ("status", "is_abnormal", "test__category")
    search_fields = ("test__name", "test__code", "result_value", "order__patient__mrn")
    autocomplete_fields = ("order", "test")
    list_select_related = ("order", "test")
