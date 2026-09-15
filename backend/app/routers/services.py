from fastapi import APIRouter, Depends, Query

from app.dependencies.auth import get_current_user
from app.models.user import User

router = APIRouter(tags=["services"])

# Static catalog for the MVP. In later milestones this is backed by the
# service_categories / service_providers tables.
_SERVICES = [
    {"id": "electricity", "name": "Electricity", "enabled": True},
    {"id": "airtime", "name": "Airtime", "enabled": True},
    {"id": "data", "name": "Data Bundles", "enabled": True},
    {"id": "water", "name": "Water", "enabled": False},
]

_PROVIDERS = {
    "electricity": [
        {"id": "eneo", "name": "ENEO", "category": "electricity"},
    ],
}


@router.get("/services")
def list_services(current_user: User = Depends(get_current_user)):
    return {"services": _SERVICES}


@router.get("/bill-payments/providers")
def list_providers(
    category: str = Query(...),
    current_user: User = Depends(get_current_user),
):
    return {"providers": _PROVIDERS.get(category, [])}
