from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services import fee_service

router = APIRouter(tags=["services"])


@router.get("/services")
def list_services(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    # Front-store service tiles are driven by Back Office service flags.
    flags = [f for f in fee_service.get_service_flags(db) if f["kind"] == "service"]
    return {
        "services": [
            {"id": f["key"], "name": f["label"], "enabled": f["enabled"]} for f in flags
        ]
    }
