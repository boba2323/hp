"""Schemas for the wards app - wards, beds and admissions.

The nested patient/doctor shapes are declared here instead of importing
``apps.patients.schemas`` / ``apps.staff.schemas`` so this app stays
self-contained.
"""

from ninja import ModelSchema, Schema

from apps.wards.models import Admission, Bed, Ward

# --- Nested shapes ----------------------------------------------------------


class WardBrief(Schema):
    id: int
    name: str
    code: str


class PatientBrief(Schema):
    id: int
    mrn: str
    full_name: str


class PatientDetailBrief(PatientBrief):
    age: int | None = None
    gender: str = ""


class StaffBrief(Schema):
    id: int
    full_name: str


# --- Wards ------------------------------------------------------------------


class WardOut(ModelSchema):
    bed_count: int
    occupied_beds: int
    available_beds: int

    class Meta:
        model = Ward
        fields = "__all__"


class WardIn(ModelSchema):
    class Meta:
        model = Ward
        fields = [
            "name",
            "code",
            "ward_type",
            "floor",
            "capacity",
            "charge_per_day",
            "description",
            "is_active",
        ]
        fields_optional = [
            "ward_type",
            "floor",
            "capacity",
            "charge_per_day",
            "description",
            "is_active",
        ]


class WardUpdateIn(ModelSchema):
    class Meta:
        model = Ward
        fields = [
            "name",
            "code",
            "ward_type",
            "floor",
            "capacity",
            "charge_per_day",
            "description",
            "is_active",
        ]
        fields_optional = "__all__"


# --- Beds -------------------------------------------------------------------


class BedOut(ModelSchema):
    ward: WardBrief
    current_patient: PatientBrief | None = None

    class Meta:
        model = Bed
        fields = ["id", "number", "status", "notes"]


class BedIn(ModelSchema):
    class Meta:
        model = Bed
        fields = ["number", "status", "notes"]
        fields_optional = ["status", "notes"]


class BedUpdateIn(ModelSchema):
    class Meta:
        model = Bed
        fields = ["number", "status", "notes"]
        fields_optional = "__all__"


class BedBrief(Schema):
    id: int
    number: str
    ward: WardBrief


# --- Occupancy --------------------------------------------------------------


class WardOccupancyOut(Schema):
    ward_id: int
    name: str
    code: str
    total_beds: int
    occupied_beds: int
    available_beds: int
    occupancy_percentage: float


class OccupancyOut(Schema):
    wards: list[WardOccupancyOut]
    total_beds: int
    occupied_beds: int
    available_beds: int
    occupancy_percentage: float


# --- Admissions -------------------------------------------------------------


class AdmissionOut(ModelSchema):
    patient: PatientDetailBrief
    bed: BedBrief
    admitting_doctor: StaffBrief
    length_of_stay_days: int

    class Meta:
        model = Admission
        fields = [
            "id",
            "admission_date",
            "discharge_date",
            "status",
            "reason",
            "diagnosis_summary",
            "notes",
            "created_at",
            "updated_at",
        ]


class AdmissionIn(ModelSchema):
    """Create body - the bed must be available at the time of admission."""

    patient: int
    bed: int
    admitting_doctor: int

    class Meta:
        model = Admission
        fields = [
            "patient",
            "bed",
            "admitting_doctor",
            "admission_date",
            "reason",
            "diagnosis_summary",
            "notes",
        ]
        fields_optional = [
            "admission_date",
            "reason",
            "diagnosis_summary",
            "notes",
        ]


class AdmissionUpdateIn(ModelSchema):
    """PATCH body.

    The bed is deliberately not updatable here: moving a patient is
    ``POST /admissions/{id}/transfer``, which also frees the old bed.
    """

    patient: int | None = None
    admitting_doctor: int | None = None

    class Meta:
        model = Admission
        fields = [
            "patient",
            "admitting_doctor",
            "admission_date",
            "discharge_date",
            "status",
            "reason",
            "diagnosis_summary",
            "notes",
        ]
        fields_optional = "__all__"


class DischargeIn(Schema):
    notes: str = ""


class TransferIn(Schema):
    bed: int
    notes: str = ""
