"""Persist and resolve support-ticket screenshots."""

import base64
import re
import uuid
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError

_DATA_URL_RE = re.compile(r"^data:image/(jpeg|jpg|png|webp);base64,(.+)$", re.I)


def upload_root() -> Path:
    root = Path(settings.SUPPORT_UPLOAD_DIR)
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_screenshot(user_id: int, image_base64: str) -> str:
    """Persist a page screenshot and return a short media reference."""
    raw = (image_base64 or "").strip()
    if not raw:
        raise ValidationError("Screenshot is required.", code="SUPPORT_SCREENSHOT_REQUIRED")

    match = _DATA_URL_RE.match(raw)
    if match:
        ext = "jpg" if match.group(1).lower() in ("jpeg", "jpg") else match.group(1).lower()
        payload = match.group(2)
    else:
        ext = "jpg"
        payload = raw

    try:
        data = base64.b64decode(payload, validate=False)
    except Exception as exc:  # noqa: BLE001
        raise ValidationError("Invalid screenshot data.", code="SUPPORT_SCREENSHOT_INVALID") from exc

    if len(data) < 100:
        raise ValidationError("Screenshot is too small.", code="SUPPORT_SCREENSHOT_INVALID")
    if len(data) > 8 * 1024 * 1024:
        raise ValidationError(
            "Screenshot is too large (max 8MB).", code="SUPPORT_SCREENSHOT_TOO_LARGE"
        )

    filename = f"{user_id}_shot_{uuid.uuid4().hex[:16]}.{ext}"
    path = upload_root() / filename
    path.write_bytes(data)
    return filename


def resolve_path(ref: str) -> Path:
    name = Path(ref or "").name
    if not name or name != ref or ".." in name:
        raise NotFoundError("Screenshot not found.", code="SUPPORT_SCREENSHOT_NOT_FOUND")
    path = upload_root() / name
    if not path.is_file():
        raise NotFoundError("Screenshot not found.", code="SUPPORT_SCREENSHOT_NOT_FOUND")
    return path
