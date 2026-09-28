from django.contrib import admin

from apps.staff.models import Department, StaffProfile


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "code",
        "location",
        "phone",
        "staff_count",
        "doctor_count",
        "is_active",
        "created_at",
    ]
    list_filter = ["is_active"]
    search_fields = ["name", "code", "location"]
    ordering = ["name"]

    @admin.display(description="Staff")
    def staff_count(self, obj):
        return obj.staff_members.count()

    @admin.display(description="Doctors")
    def doctor_count(self, obj):
        return obj.doctor_count


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = [
        "employee_id",
        "full_name",
        "role",
        "department",
        "job_title",
        "employment_type",
        "hire_date",
        "consultation_fee",
        "is_available",
    ]
    list_filter = [
        "is_available",
        "employment_type",
        "department",
        "user__role",
        "user__is_active",
    ]
    search_fields = [
        "employee_id",
        "user__username",
        "user__first_name",
        "user__last_name",
        "specialty",
        "license_number",
    ]
    autocomplete_fields = ["user", "department"]
    list_select_related = ["user", "department"]
    date_hierarchy = "hire_date"
    ordering = ["employee_id"]

    @admin.display(description="Name", ordering="user__first_name")
    def full_name(self, obj):
        return obj.full_name

    @admin.display(description="Role", ordering="user__role")
    def role(self, obj):
        return obj.user.get_role_display()
