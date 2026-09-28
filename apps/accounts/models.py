from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Single user table for the whole hospital - staff and administrators.

    Clinical detail (department, specialty, licence number) lives on
    ``staff.StaffProfile``, which points back here.
    """

    class Role(models.TextChoices):
        ADMIN = "admin", "Administrator"
        DOCTOR = "doctor", "Doctor"
        NURSE = "nurse", "Nurse"
        PHARMACIST = "pharmacist", "Pharmacist"
        LAB_TECH = "lab_tech", "Laboratory Technician"
        RECEPTIONIST = "receptionist", "Receptionist"
        ACCOUNTANT = "accountant", "Accountant"

    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.RECEPTIONIST, db_index=True
    )
    phone = models.CharField(max_length=32, blank=True)
    must_change_password = models.BooleanField(default=False)

    class Meta:
        ordering = ["first_name", "last_name", "username"]
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self) -> str:
        return self.full_name or self.username

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_doctor(self) -> bool:
        return self.role == self.Role.DOCTOR
