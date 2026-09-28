"""Root Django Ninja API - every app router is mounted here under /api/."""

from ninja import NinjaAPI
from ninja.errors import HttpError

from apps.accounts.api import router as accounts_router
from apps.appointments.api import router as appointments_router
from apps.billing.api import router as billing_router
from apps.core.api import router as core_router
from apps.laboratory.api import router as laboratory_router
from apps.patients.api import router as patients_router
from apps.pharmacy.api import router as pharmacy_router
from apps.records.api import router as records_router
from apps.staff.api import router as staff_router
from apps.wards.api import router as wards_router

api = NinjaAPI(
    title="Hospital ERP API",
    version="1.0.0",
    description="REST API for the Hospital ERP - patients, staff, appointments, "
    "EMR, pharmacy, wards, laboratory and billing.",
    # Served in every environment: the schema it renders is already public at
    # /api/openapi.json, so hiding the UI bought nothing. Gate this behind auth
    # (and set openapi_url=None) if the API surface ever needs to be private.
    docs_url="/docs",
)


@api.exception_handler(HttpError)
def on_http_error(request, exc: HttpError):
    return api.create_response(
        request,
        {"detail": exc.message, "status_code": exc.status_code},
        status=exc.status_code,
    )


api.add_router("/auth", accounts_router)
api.add_router("/core", core_router)
api.add_router("/staff", staff_router)
api.add_router("/patients", patients_router)
api.add_router("/appointments", appointments_router)
api.add_router("/records", records_router)
api.add_router("/pharmacy", pharmacy_router)
api.add_router("/wards", wards_router)
api.add_router("/laboratory", laboratory_router)
api.add_router("/billing", billing_router)
