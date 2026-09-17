import base64
import re
import uuid
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError

KINDS = {
    "front": "id_document_ref",
    "back": "id_document_back_ref",
    "selfie": "selfie_ref",
}

_DATA_URL_RE = re.compile(r"^data:image/(jpeg|jpg|png|webp);base64,(.+)$", re.I)


def upload_root() -> Path:
    root = Path(settings.KYC_UPLOAD_DIR)
    root.mkdir(parents=True, exist_ok=True)
    return root


def field_for_kind(kind: str) -> str:
    if kind not in KINDS:
        raise ValidationError(
            "Capture kind must be front, back, or selfie.",
            code="KYC_CAPTURE_KIND_INVALID",
        )
    return KINDS[kind]


def save_capture(user_id: int, kind: str, image_base64: str) -> str:
    """Persist a camera JPEG/PNG and return a short media reference."""
    field_for_kind(kind)
    raw = (image_base64 or "").strip()
    if not raw:
        raise ValidationError("Image capture is required.", code="KYC_CAPTURE_REQUIRED")

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
        raise ValidationError("Invalid image data.", code="KYC_CAPTURE_INVALID") from exc

    if len(data) < 100:
        raise ValidationError("Captured image is too small.", code="KYC_CAPTURE_INVALID")
    if len(data) > 8 * 1024 * 1024:
        raise ValidationError("Captured image is too large (max 8MB).", code="KYC_CAPTURE_TOO_LARGE")

    filename = f"{user_id}_{kind}_{uuid.uuid4().hex[:16]}.{ext}"
    path = upload_root() / filename
    path.write_bytes(data)
    return filename


def resolve_path(ref: str) -> Path:
    name = Path(ref or "").name
    if not name or name != ref or ".." in name:
        raise NotFoundError("Capture not found.", code="KYC_CAPTURE_NOT_FOUND")
    path = upload_root() / name
    if not path.is_file():
        raise NotFoundError("Capture not found.", code="KYC_CAPTURE_NOT_FOUND")
    return path


def owned_by(ref: str, user_id: int) -> bool:
    name = Path(ref or "").name
    return name.startswith(f"{user_id}_")
