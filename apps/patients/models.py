from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.codes import next_code


class Patient(models.Model):
    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"

    class BloodGroup(models.TextChoices):
        A_POS = "A+", "A+"
        A_NEG = "A-", "A-"
        B_POS = "B+", "B+"
        B_NEG = "B-", "B-"
        AB_POS = "AB+", "AB+"
        AB_NEG = "AB-", "AB-"
        O_POS = "O+", "O+"
        O_NEG = "O-", "O-"

    class MaritalStatus(models.TextChoices):
        SINGLE = "single", "Single"
        MARRIED = "married", "Married"
        DIVORCED = "divorced", "Divorced"
        WIDOWED = "widowed", "Widowed"

    mrn = models.CharField(
        max_length=20, unique=True, blank=True, verbose_name="Medical record number"
    )

    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=16, choices=Gender.choices, blank=True)
    blood_group = models.CharField(
        max_length=8, choices=BloodGroup.choices, blank=True
    )
    marital_status = models.CharField(
        max_length=16, choices=MaritalStatus.choices, blank=True
    )
    national_id = models.CharField(max_length=64, unique=True, null=True, blank=True)

    phone = models.CharField(max_length=32, blank=True)
    alt_phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80, blank=True)
    postal_code = models.CharField(max_length=16, blank=True)
    occupation = models.CharField(max_length=120, blank=True)

    allergies = models.TextField(blank=True, help_text="Comma separated")
    chronic_conditions = models.TextField(blank=True)

    emergency_contact_name = models.CharField(max_length=120, blank=True)
    emergency_contact_relationship = models.CharField(max_length=64, blank=True)
    emergency_contact_phone = models.CharField(max_length=32, blank=True)

    insurance_provider = models.CharField(max_length=120, blank=True)
    insurance_policy_number = models.CharField(max_length=64, blank=True)

    is_active = models.BooleanField(default=True)
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registered_patients",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["last_name", "first_name"]),
            models.Index(fields=["phone"]),
        ]

    def __str__(self) -> str:
        return f"{self.mrn} - {self.full_name}"

    def save(self, *args, **kwargs):
        if not self.mrn:
            self.mrn = next_code(Patient, "mrn", "MRN-")
        super().save(*args, **kwargs)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def age(self) -> int | None:
        if not self.date_of_birth:
            return None
        today = timezone.localdate()
        born = self.date_of_birth
        return (
            today.year
            - born.year
            - ((today.month, today.day) < (born.month, born.day))
        )
