from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError
from app.core.security import decode_token
from app.db.database import get_db
from app.models.user import User, UserStatus

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise AuthError("Authentication required.", code="AUTH_REQUIRED")
    try:
        payload = decode_token(credentials.credentials)
    except Exception:
        raise AuthError("Invalid or expired token.", code="INVALID_TOKEN")
    if payload.get("type") != "access":
        raise AuthError("Invalid token type.", code="INVALID_TOKEN_TYPE")
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise AuthError("Invalid token subject.", code="INVALID_TOKEN")

    user = db.get(User, user_id)
    if not user:
        raise AuthError("User not found.", code="USER_NOT_FOUND")
    if user.status != UserStatus.ACTIVE:
        raise AuthError("Account is not active.", code="ACCOUNT_INACTIVE")
    return user
