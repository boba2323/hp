"""Populate the database with a realistic demo hospital.

    uv run python manage.py seed_demo          # skip if data already present
    uv run python manage.py seed_demo --reset  # wipe demo data and rebuild
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.appointments.models import Appointment
from apps.billing.models import Invoice, InvoiceItem, Payment
from apps.laboratory.models import LabOrder, LabOrderItem, LabTest
from apps.patients.models import Patient
from apps.pharmacy.models import Dispense, Medication, StockBatch
from apps.records.models import Diagnosis, Encounter, Prescription
from apps.staff.models import Department, StaffProfile
from apps.wards.models import Admission, Bed, Ward

DEMO_PASSWORD = "Hospital123!"

FIRST_NAMES = [
    "Bhaskar", "Anima", "Pranab", "Bornali", "Dhruba", "Pallabi", "Nayan", "Jyotsna",
    "Rupam", "Tarali", "Sanjib", "Manashi", "Utpal", "Nilima", "Parag", "Junali",
    "Ranjan", "Dipali", "Arup", "Nabanita", "Gautam", "Chandana", "Jayanta", "Rupali",
]
LAST_NAMES = [
    "Baruah", "Gogoi", "Das", "Saikia", "Deka", "Kalita", "Hazarika", "Bora",
    "Mahanta", "Phukan", "Sarma", "Nath", "Choudhury", "Talukdar",
]
CITIES = [
    "Guwahati", "Dibrugarh", "Silchar", "Jorhat", "Nagaon", "Tezpur", "Tinsukia",
]
ALLERGIES = ["Penicillin", "Sulfa drugs", "Aspirin", "Latex", "Peanuts", ""]
CONDITIONS = ["Hypertension", "Type 2 Diabetes", "Asthma", "Sickle cell trait", ""]
COMPLAINTS = [
    "Persistent headache and fever for 3 days",
    "Chest pain on exertion",
    "Recurrent abdominal pain",
    "Cough and difficulty breathing",
    "Painful urination",
    "Generalised body weakness",
    "Skin rash and itching",
    "Blurred vision",
]
DIAGNOSES = [
    ("B54", "Unspecified malaria"),
    ("J06.9", "Acute upper respiratory infection"),
    ("I10", "Essential hypertension"),
    ("E11.9", "Type 2 diabetes mellitus"),
    ("K30", "Functional dyspepsia"),
    ("N39.0", "Urinary tract infection"),
    ("L30.9", "Dermatitis, unspecified"),
    ("A09", "Infectious gastroenteritis"),
]
MEDICATIONS = [
    ("Paracetamol", "Acetaminophen", "Analgesic", "tablet", "500mg", "5.00"),
    ("Amoxicillin", "Amoxicillin", "Antibiotic", "capsule", "500mg", "25.00"),
    ("Artemether/Lumefantrine", "Artemether", "Antimalarial", "tablet", "20/120mg", "45.00"),
    ("Metformin", "Metformin HCl", "Antidiabetic", "tablet", "500mg", "18.00"),
    ("Amlodipine", "Amlodipine besylate", "Antihypertensive", "tablet", "5mg", "22.00"),
    ("Ibuprofen", "Ibuprofen", "NSAID", "tablet", "400mg", "12.00"),
    ("Cetirizine", "Cetirizine HCl", "Antihistamine", "tablet", "10mg", "8.00"),
    ("Salbutamol", "Albuterol", "Bronchodilator", "inhaler", "100mcg", "120.00"),
    ("Omeprazole", "Omeprazole", "Antacid", "capsule", "20mg", "30.00"),
    ("Ceftriaxone", "Ceftriaxone", "Antibiotic", "injection", "1g", "95.00"),
    ("ORS", "Oral rehydration salts", "Rehydration", "other", "1 sachet", "3.00"),
    ("Diclofenac", "Diclofenac sodium", "NSAID", "injection", "75mg", "40.00"),
]
LAB_TESTS = [
    ("Complete blood count", "CBC", "hematology", "Blood", "45.00", "4-11 x10^9/L"),
    ("Malaria parasite test", "MP", "microbiology", "Blood", "25.00", "Negative"),
    ("Fasting blood glucose", "FBG", "chemistry", "Blood", "20.00", "3.9-5.6 mmol/L"),
    ("Urinalysis", "UA", "urinalysis", "Urine", "15.00", "Normal"),
    ("Liver function test", "LFT", "chemistry", "Blood", "70.00", "Within range"),
    ("Chest X-ray", "CXR", "imaging", "N/A", "150.00", "No consolidation"),
    ("HIV screening", "HIV", "microbiology", "Blood", "35.00", "Non-reactive"),
    ("Lipid profile", "LIPID", "chemistry", "Blood", "60.00", "TC < 5.2 mmol/L"),
    ("Erythrocyte sedimentation rate", "ESR", "hematology", "Blood", "18.00", "0-20 mm/hr"),
    ("Stool microscopy", "STOOL", "microbiology", "Stool", "22.00", "No ova/cyst"),
]
DEPARTMENTS = [
    ("General Medicine", "GEN", "Ward 1"),
    ("Paediatrics", "PAED", "Ward 2"),
    ("Obstetrics & Gynaecology", "OBGY", "Ward 3"),
    ("Surgery", "SURG", "Ward 4"),
    ("Cardiology", "CARD", "Ward 1"),
    ("Emergency", "EMER", "Ground floor"),
    ("Laboratory", "LAB", "Basement"),
    ("Pharmacy", "PHAR", "Ground floor"),
]
STAFF = [
    ("dr.baruah", "Bhaskar", "Baruah", "doctor", "Consultant Physician", "Cardiology", "full_time"),
    ("dr.gogoi", "Pranab", "Gogoi", "doctor", "Consultant Surgeon", "Surgery", "full_time"),
    ("dr.das", "Anima", "Das", "doctor", "Paediatrician", "Paediatrics", "full_time"),
    ("dr.saikia", "Jyotsna", "Saikia", "doctor", "Obstetrician", "Obstetrics & Gynaecology", "full_time"),
    ("dr.deka", "Dhruba", "Deka", "doctor", "Emergency Physician", "Emergency", "part_time"),
    ("nurse.bornali", "Bornali", "Kalita", "nurse", "Head Nurse", "General Medicine", "full_time"),
    ("nurse.rupam", "Rupam", "Bora", "nurse", "Staff Nurse", "Paediatrics", "full_time"),
    ("pharm.pallabi", "Pallabi", "Hazarika", "pharmacist", "Chief Pharmacist", "Pharmacy", "full_time"),
    ("lab.nayan", "Nayan", "Phukan", "lab_tech", "Laboratory Scientist", "Laboratory", "full_time"),
    ("front.desk", "Junali", "Talukdar", "receptionist", "Front Desk Officer", "General Medicine", "full_time"),
    ("acct.tarali", "Tarali", "Mahanta", "accountant", "Billing Officer", "General Medicine", "full_time"),
]


class Command(BaseCommand):
    help = "Seed the database with demo hospital data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing demo data before seeding",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(42)

        if options["reset"]:
            self._reset()

        if Patient.objects.exists() and not options["reset"]:
            self.stdout.write(
                self.style.WARNING(
                    "Data already present - nothing to do. Use --reset to rebuild."
                )
            )
            return

        departments = self._departments()
        staff = self._staff(departments)
        medications = self._medications()
        lab_tests = self._lab_tests()
        wards, beds = self._wards()
        patients = self._patients()
        appointments = self._appointments(patients, staff)
        self._clinical(patients, staff, appointments, medications, lab_tests, departments)
        self._admissions(patients, staff, beds)
        self._billing(patients, staff, appointments)

        self._summary()

    # --- builders -----------------------------------------------------------

    def _reset(self):
        self.stdout.write("Clearing existing data...")
        for model in (
            Payment, InvoiceItem, Invoice, LabOrderItem, LabOrder, Dispense,
            Prescription, Diagnosis, Encounter, Appointment, Admission, Bed, Ward,
            StockBatch, Medication, LabTest, StaffProfile, Department, Patient,
        ):
            model.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()

    def _departments(self):
        created = []
        for name, code, location in DEPARTMENTS:
            dept, _ = Department.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "location": location,
                    "phone": f"+91-361-{random.randint(2000000, 2999999)}",
                    "description": f"{name} department",
                },
            )
            created.append(dept)
        self.stdout.write(f"  departments: {len(created)}")
        return {dept.name: dept for dept in created}

    def _staff(self, departments):
        admin, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@hospital.test",
                "first_name": "System",
                "last_name": "Administrator",
                "role": User.Role.ADMIN,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created:
            admin.set_password(DEMO_PASSWORD)
            admin.save()

        profiles = []
        for index, (username, first, last, role, title, dept_name, employment) in enumerate(
            STAFF, start=1
        ):
            user, made = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@hospital.test",
                    "first_name": first,
                    "last_name": last,
                    "role": role,
                    "phone": f"+91-98{random.randint(100000000, 999999999)}",
                },
            )
            if made:
                user.set_password(DEMO_PASSWORD)
                user.save()

            profile, _ = StaffProfile.objects.get_or_create(
                user=user,
                defaults={
                    "employee_id": f"EMP-{index:05d}",
                    "department": departments.get(dept_name),
                    "job_title": title,
                    "employment_type": employment,
                    "specialty": title,
                    "license_number": f"LIC-{random.randint(100000, 999999)}",
                    "hire_date": timezone.localdate() - timedelta(days=random.randint(200, 3000)),
                    "consultation_fee": Decimal(random.choice(["2500.00", "3500.00", "5000.00", "7500.00"])),
                },
            )
            profiles.append(profile)
        self.stdout.write(f"  staff: {len(profiles) + 1} users")
        return profiles

    def _medications(self):
        created = []
        for name, generic, category, form, strength, price in MEDICATIONS:
            med, _ = Medication.objects.get_or_create(
                name=name,
                strength=strength,
                defaults={
                    "generic_name": generic,
                    "brand_name": name,
                    "category": category,
                    "form": form,
                    "unit_price": Decimal(price),
                    "cost_price": (Decimal(price) * Decimal("0.6")).quantize(Decimal("0.01")),
                    "reorder_level": random.choice([20, 30, 50]),
                    "is_controlled": name in {"Ceftriaxone", "Diclofenac"},
                },
            )
            created.append(med)

            if not med.batches.exists():
                for batch_index in range(random.randint(1, 3)):
                    quantity = random.randint(40, 300)
                    received = timezone.localdate() - timedelta(days=random.randint(10, 200))
                    # A few batches deliberately sit near expiry for the alerts view.
                    shelf_life = random.choice([30, 60, 120, 400, 700])
                    StockBatch.objects.create(
                        medication=med,
                        batch_number=f"B{med.id:03d}-{batch_index + 1}",
                        quantity_received=quantity,
                        quantity_remaining=random.randint(0, quantity),
                        unit_cost=(Decimal(price) * Decimal("0.6")).quantize(Decimal("0.01")),
                        supplier=random.choice(["Cipla", "Sun Pharmaceutical", "Dr. Reddy's Laboratories", "Zydus Lifesciences", "Lupin"]),
                        received_date=received,
                        expiry_date=received + timedelta(days=shelf_life),
                    )
        self.stdout.write(f"  medications: {len(created)}")
        return created

    def _lab_tests(self):
        created = []
        for name, code, category, sample, price, normal in LAB_TESTS:
            test, _ = LabTest.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "category": category,
                    "sample_type": sample,
                    "price": Decimal(price),
                    "normal_range": normal,
                    "turnaround_hours": random.choice([2, 4, 12, 24, 48]),
                },
            )
            created.append(test)
        self.stdout.write(f"  lab tests: {len(created)}")
        return created

    def _wards(self):
        layout = [
            ("General Ward A", "GWA", "general", "1", 12, "5000.00"),
            ("General Ward B", "GWB", "general", "1", 12, "5000.00"),
            ("Private Wing", "PVT", "private", "3", 6, "25000.00"),
            ("Intensive Care Unit", "ICU", "icu", "2", 4, "50000.00"),
            ("Maternity Ward", "MAT", "maternity", "2", 8, "15000.00"),
            ("Paediatric Ward", "PAED", "pediatric", "2", 10, "8000.00"),
        ]
        wards, beds = [], []
        for name, code, ward_type, floor, capacity, charge in layout:
            ward, _ = Ward.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "ward_type": ward_type,
                    "floor": floor,
                    "capacity": capacity,
                    "charge_per_day": Decimal(charge),
                },
            )
            wards.append(ward)
            for number in range(1, capacity + 1):
                bed, _ = Bed.objects.get_or_create(
                    ward=ward, number=f"{number:02d}", defaults={"status": Bed.Status.AVAILABLE}
                )
                beds.append(bed)
        self.stdout.write(f"  wards: {len(wards)}, beds: {len(beds)}")
        return wards, beds

    def _patients(self):
        created = []
        for index in range(60):
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            dob = timezone.localdate() - timedelta(days=random.randint(365, 90 * 365))
            patient = Patient.objects.create(
                first_name=first,
                last_name=last,
                date_of_birth=dob,
                gender=random.choice([Patient.Gender.MALE, Patient.Gender.FEMALE]),
                blood_group=random.choice([c[0] for c in Patient.BloodGroup.choices]),
                marital_status=random.choice([c[0] for c in Patient.MaritalStatus.choices]),
                phone=f"+91-70{random.randint(100000000, 999999999)}",
                email=f"{first.lower()}.{last.lower()}{index}@example.com",
                address=f"{random.randint(1, 200)} {random.choice(['GS Road', 'MG Road', 'AT Road', 'Beltola Road', 'Zoo Road'])}",
                city=random.choice(CITIES),
                state=random.choice(CITIES),
                occupation=random.choice(["Teacher", "Trader", "Engineer", "Farmer", "Civil servant", "Student"]),
                allergies=random.choice(ALLERGIES),
                chronic_conditions=random.choice(CONDITIONS),
                emergency_contact_name=f"{random.choice(FIRST_NAMES)} {last}",
                emergency_contact_relationship=random.choice(["Spouse", "Sibling", "Parent", "Child"]),
                emergency_contact_phone=f"+91-84{random.randint(100000000, 999999999)}",
                insurance_provider=random.choice(["NHIS", "Hygeia HMO", "Reliance HMO", ""]),
                insurance_policy_number=f"POL-{random.randint(100000, 999999)}",
            )
            created.append(patient)
        self.stdout.write(f"  patients: {len(created)}")
        return created

    def _appointments(self, patients, staff):
        doctors = [s for s in staff if s.user.role == User.Role.DOCTOR]
        created = []
        now = timezone.now()
        statuses = (
            [Appointment.Status.COMPLETED] * 6
            + [Appointment.Status.SCHEDULED] * 2
            + [Appointment.Status.CANCELLED]
            + [Appointment.Status.NO_SHOW]
        )

        for patient in patients:
            for _ in range(random.randint(1, 3)):
                doctor = random.choice(doctors)
                day_offset = random.randint(-45, 21)
                hour = random.randint(8, 16)
                start = (now + timedelta(days=day_offset)).replace(
                    hour=hour, minute=random.choice([0, 15, 30, 45]), second=0, microsecond=0
                )
                end = start + timedelta(minutes=random.choice([15, 30, 45]))

                if day_offset < 0:
                    status = random.choice(statuses)
                elif day_offset == 0:
                    status = random.choice(
                        [Appointment.Status.CHECKED_IN, Appointment.Status.IN_PROGRESS,
                         Appointment.Status.CONFIRMED, Appointment.Status.SCHEDULED]
                    )
                else:
                    status = random.choice([Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED])

                created.append(
                    Appointment.objects.create(
                        patient=patient,
                        doctor=doctor,
                        department=doctor.department,
                        scheduled_start=start,
                        scheduled_end=end,
                        status=status,
                        appointment_type=random.choice([c[0] for c in Appointment.Type.choices]),
                        reason=random.choice(COMPLAINTS),
                        cancellation_reason="Patient rescheduled" if status == Appointment.Status.CANCELLED else "",
                    )
                )
        self.stdout.write(f"  appointments: {len(created)}")
        return created

    def _clinical(self, patients, staff, appointments, medications, lab_tests, departments):
        completed = [a for a in appointments if a.status == Appointment.Status.COMPLETED]
        encounters = []

        for appointment in completed:
            encounter = Encounter.objects.create(
                patient=appointment.patient,
                doctor=appointment.doctor,
                appointment=appointment,
                encounter_type=random.choice([c[0] for c in Encounter.Type.choices]),
                encounter_date=appointment.scheduled_start + timedelta(minutes=20),
                chief_complaint=appointment.reason,
                history_of_present_illness="Patient reports onset over the past few days. No prior episode of note.",
                examination_notes="Alert and oriented. Chest clear. Abdomen soft, non-tender.",
                treatment_plan="Symptomatic treatment, review in one week if unresolved.",
                temperature_c=Decimal(str(round(random.uniform(36.0, 39.2), 1))),
                bp_systolic=random.randint(100, 165),
                bp_diastolic=random.randint(60, 100),
                pulse=random.randint(58, 110),
                respiratory_rate=random.randint(12, 24),
                spo2=random.randint(93, 100),
                weight_kg=Decimal(str(round(random.uniform(45, 105), 2))),
                height_cm=Decimal(str(round(random.uniform(150, 195), 2))),
                status=random.choice([Encounter.Status.CLOSED] * 4 + [Encounter.Status.OPEN]),
                follow_up_date=timezone.localdate() + timedelta(days=random.randint(3, 30)),
            )
            encounters.append(encounter)

            for order, (code, description) in enumerate(
                random.sample(DIAGNOSES, random.randint(1, 2))
            ):
                Diagnosis.objects.create(
                    encounter=encounter,
                    code=code,
                    description=description,
                    diagnosis_type=Diagnosis.Type.PRIMARY if order == 0 else Diagnosis.Type.SECONDARY,
                )

            for medication in random.sample(medications, random.randint(1, 3)):
                quantity = random.randint(6, 30)
                prescription = Prescription.objects.create(
                    encounter=encounter,
                    patient=encounter.patient,
                    doctor=encounter.doctor,
                    medication=medication,
                    dosage=medication.strength or "1 tab",
                    frequency=random.choice(["once daily", "twice daily", "three times daily"]),
                    duration_days=random.randint(3, 14),
                    quantity=quantity,
                    instructions="Take after food with plenty of water.",
                    status=Prescription.Status.PENDING,
                )

                # Most older prescriptions have already been handed out.
                if random.random() < 0.75:
                    batch = (
                        medication.batches.filter(quantity_remaining__gte=quantity).first()
                    )
                    if batch:
                        batch.quantity_remaining -= quantity
                        batch.save(update_fields=["quantity_remaining"])
                        Prescription.objects.filter(pk=prescription.pk).update(
                            status=Prescription.Status.DISPENSED
                        )
                        Dispense.objects.create(
                            prescription=prescription,
                            patient=encounter.patient,
                            batch=batch,
                            quantity_dispensed=quantity,
                            dispensed_by=next(
                                (s.user for s in staff if s.user.role == User.Role.PHARMACIST),
                                None,
                            ),
                            notes="Dispensed at outpatient pharmacy.",
                        )

        self.stdout.write(f"  encounters: {len(encounters)}")

        # Laboratory orders
        orders = []
        for encounter in random.sample(encounters, k=max(1, len(encounters) // 2)):
            order = LabOrder.objects.create(
                patient=encounter.patient,
                ordered_by=encounter.doctor,
                encounter=encounter,
                priority=random.choice([c[0] for c in LabOrder.Priority.choices]),
                ordered_at=encounter.encounter_date + timedelta(minutes=30),
            )
            for test in random.sample(lab_tests, random.randint(1, 3)):
                item = LabOrderItem(order=order, test=test, price=test.price)
                if random.random() < 0.8:
                    item.result_value = f"{round(random.uniform(1, 100), 1)}"
                    item.result_unit = test.unit or ""
                    item.is_abnormal = random.random() < 0.25
                    item.remarks = "Repeat in 2 weeks" if item.is_abnormal else ""
                item.save()
            orders.append(order)

        for order in orders:
            if order.items.exclude(result_value="").count() == order.items.count():
                order.status = LabOrder.Status.COMPLETED
                order.completed_at = order.ordered_at + timedelta(hours=random.randint(2, 48))
                order.save(update_fields=["status", "completed_at"])

        self.stdout.write(f"  lab orders: {len(orders)}")

    def _admissions(self, patients, staff, beds):
        doctors = [s for s in staff if s.user.role == User.Role.DOCTOR]
        available = [b for b in beds if b.ward.ward_type != Ward.Type.ICU]
        admitted = []

        for patient in random.sample(patients, k=18):
            bed = None
            for candidate in random.sample(available, k=len(available)):
                if Admission.objects.filter(
                    bed=candidate, status=Admission.Status.ADMITTED
                ).exists():
                    continue
                if candidate.status == Bed.Status.MAINTENANCE:
                    continue
                bed = candidate
                break
            if bed is None:
                break

            admission_date = timezone.now() - timedelta(days=random.randint(0, 20))
            # Two thirds are still in hospital, the rest have gone home.
            still_in = random.random() < 0.66
            admission = Admission.objects.create(
                patient=patient,
                bed=bed,
                admitting_doctor=random.choice(doctors),
                admission_date=admission_date,
                status=Admission.Status.ADMITTED,
                reason=random.choice(COMPLAINTS),
                diagnosis_summary=random.choice(DIAGNOSES)[1],
            )
            if not still_in:
                admission.status = Admission.Status.DISCHARGED
                admission.discharge_date = admission_date + timedelta(days=random.randint(1, 10))
                admission.discharged_by = next(
                    (s.user for s in staff if s.user.role == User.Role.DOCTOR), None
                )
                admission.save()
            admitted.append(admission)

        Ward.objects.all().update()  # no-op touch to keep the summary honest
        self.stdout.write(f"  admissions: {len(admitted)}")
        return admitted

    def _billing(self, patients, staff, appointments):
        accountant = next((s.user for s in staff if s.user.role == User.Role.ACCOUNTANT), None)
        completed = [a for a in appointments if a.status == Appointment.Status.COMPLETED]
        invoices = []

        for appointment in completed[:60]:
            invoice = Invoice.objects.create(
                patient=appointment.patient,
                encounter=getattr(appointment, "encounter", None),
                issued_date=appointment.scheduled_start.date(),
                due_date=appointment.scheduled_start.date() + timedelta(days=14),
                tax_rate=Decimal("7.50"),
                created_by=accountant,
                notes="Consultation and associated charges.",
            )
            InvoiceItem.objects.create(
                invoice=invoice,
                item_type=InvoiceItem.Type.CONSULTATION,
                description=f"Consultation - {appointment.doctor.full_name}",
                quantity=1,
                unit_price=appointment.doctor.consultation_fee,
            )
            for item in random.sample(
                [
                    (InvoiceItem.Type.LABORATORY, "Laboratory investigation", "45.00"),
                    (InvoiceItem.Type.PHARMACY, "Prescribed medication", "60.00"),
                    (InvoiceItem.Type.PROCEDURE, "Dressing change", "35.00"),
                    (InvoiceItem.Type.BED, "Observation bed (per day)", "5000.00"),
                ],
                random.randint(0, 3),
            ):
                InvoiceItem.objects.create(
                    invoice=invoice,
                    item_type=item[0],
                    description=item[1],
                    quantity=random.randint(1, 3),
                    unit_price=Decimal(item[2]),
                )

            invoice.recalculate()

            roll = random.random()
            if roll < 0.55:
                Payment.objects.create(
                    invoice=invoice, amount=invoice.total, method=Payment.Method.CASH,
                    received_by=accountant, reference=f"RCPT-{random.randint(10000, 99999)}",
                )
            elif roll < 0.8:
                Payment.objects.create(
                    invoice=invoice,
                    amount=(invoice.total * Decimal("0.5")).quantize(Decimal("0.01")),
                    method=Payment.Method.CARD,
                    received_by=accountant,
                    reference=f"POS-{random.randint(10000, 99999)}",
                )
            invoice.refresh_from_db()
            invoices.append(invoice)

        self.stdout.write(f"  invoices: {len(invoices)}")

    def _summary(self):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Demo hospital seeded."))
        self.stdout.write("")
        self.stdout.write(f"  Login:    admin / {DEMO_PASSWORD}          (administrator)")
        self.stdout.write(f"  Doctor:   dr.baruah / {DEMO_PASSWORD}")
        self.stdout.write(f"  Nurse:    nurse.bornali / {DEMO_PASSWORD}")
        self.stdout.write(f"  Pharmacy: pharm.pallabi / {DEMO_PASSWORD}")
        self.stdout.write(f"  Lab:      lab.nayan / {DEMO_PASSWORD}")
        self.stdout.write(f"  Billing:  acct.tarali / {DEMO_PASSWORD}")
        self.stdout.write("")
