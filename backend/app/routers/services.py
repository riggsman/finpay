from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.catalog import ServiceProvider
from app.models.user import User
from app.services import fee_service

router = APIRouter(tags=["services"])


@router.get("/services")
def list_services(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    # Front-store tiles only include services the admin has enabled.
    flags = [
        f
        for f in fee_service.get_service_flags(db)
        if f["kind"] == "service" and f["enabled"]
    ]
    icons: dict[str, str | None] = {}
    for p in (
        db.query(ServiceProvider)
        .filter(ServiceProvider.enabled.is_(True))
        .order_by(ServiceProvider.sort_order.asc(), ServiceProvider.id.asc())
        .all()
    ):
        if p.category not in icons and p.icon:
            icons[p.category] = p.icon
    return {
        "services": [
            {
                "id": f["key"],
                "name": f["label"],
                "enabled": True,
                "icon": icons.get(f["key"]),
            }
            for f in flags
        ]
    }
