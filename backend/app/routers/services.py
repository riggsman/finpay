from fastapi import APIRouter, Depends

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


@router.get("/services")
def list_services(current_user: User = Depends(get_current_user)):
    return {"services": _SERVICES}
