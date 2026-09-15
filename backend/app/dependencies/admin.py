from fastapi import Depends

from app.core.exceptions import AppError
from app.dependencies.auth import get_current_user
from app.models.user import User


def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise AppError("Administrator access required.", code="ADMIN_REQUIRED",
                       status_code=403)
    return current_user
