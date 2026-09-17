"""Embedded local mail catcher for development (Windows-friendly, no Docker).

Started automatically with the backend lifespan when DEV_MAIL_SERVER_ENABLED
is true (default in development). Provides:

  - SMTP on DEV_MAIL_SMTP_HOST:DEV_MAIL_SMTP_PORT (default 127.0.0.1:1025)
  - Web inbox on http://DEV_MAIL_WEB_HOST:DEV_MAIL_WEB_PORT (default :1080)
"""

from __future__ import annotations

import email
import html
import json
import os
import socket
import threading
from datetime import datetime, timezone
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger("finpay.dev_mail")

ROOT = Path(__file__).resolve().parents[2]
MAIL_DIR = ROOT / "tmp" / "dev_mail"

_controller = None
_httpd: ThreadingHTTPServer | None = None
_http_thread: threading.Thread | None = None
_started = False


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


class CaptureHandler:
    async def handle_DATA(self, server, session, envelope):  # noqa: N802
        MAIL_DIR.mkdir(parents=True, exist_ok=True)
        raw = envelope.content
        if isinstance(raw, str):
            raw = raw.encode("utf-8", errors="replace")

        msg = email.message_from_bytes(raw, policy=default)
        meta = {
            "id": _now_stamp(),
            "peer": getattr(session, "peer", None),
            "mail_from": envelope.mail_from,
            "rcpt_tos": list(envelope.rcpt_tos or []),
            "subject": str(msg.get("subject") or "(no subject)"),
            "received_at": datetime.now(timezone.utc).isoformat(),
        }
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/plain":
                    body = part.get_content()
                    break
                if ctype == "text/html" and not body:
                    body = part.get_content()
        else:
            body = msg.get_content()

        meta["body"] = body if isinstance(body, str) else str(body)
        (MAIL_DIR / f"{meta['id']}.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )
        (MAIL_DIR / f"{meta['id']}.eml").write_bytes(raw)
        logger.info(
            "Dev mail captured subject=%s to=%s",
            meta["subject"],
            ",".join(meta["rcpt_tos"]),
        )
        return "250 Message accepted"


def _list_messages() -> list[dict]:
    if not MAIL_DIR.exists():
        return []
    rows = []
    for path in sorted(MAIL_DIR.glob("*.json"), reverse=True):
        try:
            rows.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return rows


def _render_inbox(messages: list[dict]) -> str:
    items = []
    for m in messages:
        mid = html.escape(m.get("id", ""))
        subj = html.escape(m.get("subject", ""))
        to = html.escape(", ".join(m.get("rcpt_tos") or []))
        when = html.escape(m.get("received_at", ""))
        items.append(
            f'<li><a href="/message/{mid}"><strong>{subj}</strong></a>'
            f"<div class='meta'>To: {to}<br/>{when}</div></li>"
        )
    body = (
        "\n".join(items)
        or "<li class='empty'>No emails captured yet. Trigger a FinPay notification.</li>"
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"/><title>FinPay Dev Mail</title>
<style>
body{{font-family:Segoe UI,sans-serif;margin:24px;background:#f4f7fc;color:#101828}}
h1{{margin:0 0 8px}} .sub{{color:#667085;margin-bottom:20px}}
ul{{list-style:none;padding:0;margin:0;display:grid;gap:10px}}
li{{background:#fff;border:1px solid #e4e7ec;border-radius:12px;padding:14px}}
li.empty{{color:#667085}}
a{{color:#1a56db;text-decoration:none}}
.meta{{font-size:13px;color:#667085;margin-top:6px}}
.actions{{margin-bottom:16px}}
button{{background:#1a56db;color:#fff;border:0;border-radius:8px;padding:8px 12px;cursor:pointer}}
</style></head><body>
<h1>FinPay Dev Mail</h1>
<p class="sub">Local SMTP catcher · started with the FinPay backend · no Docker</p>
<div class="actions"><form method="post" action="/clear"><button type="submit">Clear inbox</button></form></div>
<ul>{body}</ul>
</body></html>"""


def _render_message(msg: dict) -> str:
    subj = html.escape(msg.get("subject", ""))
    to = html.escape(", ".join(msg.get("rcpt_tos") or []))
    frm = html.escape(str(msg.get("mail_from") or ""))
    when = html.escape(msg.get("received_at", ""))
    body = html.escape(msg.get("body") or "")
    return f"""<!doctype html>
<html><head><meta charset="utf-8"/><title>{subj}</title>
<style>
body{{font-family:Segoe UI,sans-serif;margin:24px;background:#f4f7fc;color:#101828}}
.card{{background:#fff;border:1px solid #e4e7ec;border-radius:12px;padding:18px;max-width:820px}}
.meta{{color:#667085;font-size:13px;margin:8px 0 16px}}
pre{{white-space:pre-wrap;word-break:break-word;background:#f9fafb;padding:14px;border-radius:10px}}
a{{color:#1a56db}}
</style></head><body>
<p><a href="/">← Inbox</a></p>
<div class="card">
  <h1>{subj}</h1>
  <div class="meta">From: {frm}<br/>To: {to}<br/>{when}</div>
  <pre>{body}</pre>
</div>
</body></html>"""


class InboxHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_GET(self):  # noqa: N802
        if self.path in ("/", "/index.html"):
            self._ok(_render_inbox(_list_messages()).encode("utf-8"))
            return
        if self.path.startswith("/message/"):
            mid = self.path.split("/message/", 1)[1].strip("/")
            path = MAIL_DIR / f"{mid}.json"
            if not path.is_file():
                self.send_error(404)
                return
            msg = json.loads(path.read_text(encoding="utf-8"))
            self._ok(_render_message(msg).encode("utf-8"))
            return
        self.send_error(404)

    def do_POST(self):  # noqa: N802
        if self.path == "/clear":
            if MAIL_DIR.exists():
                for p in MAIL_DIR.glob("*"):
                    if p.is_file():
                        p.unlink(missing_ok=True)
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
            return
        self.send_error(404)

    def _ok(self, content: bytes):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def should_start() -> bool:
    """Whether the embedded mail catcher should run with the API process."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    from app.core.config import settings

    if not settings.DEV_MAIL_SERVER_ENABLED:
        return False
    env = (settings.ENVIRONMENT or "").lower()
    return env in ("development", "dev", "local")


def wire_email_to_dev_mail() -> None:
    """Point FinPay SMTP settings at the embedded catcher when safe to do so."""
    from app.core.config import settings

    remote = (settings.SMTP_HOST or "").strip().lower()
    if remote and remote not in ("127.0.0.1", "localhost", ""):
        return
    if settings.EMAIL_BACKEND.lower() == "disabled":
        return

    settings.EMAIL_BACKEND = "smtp"
    settings.SMTP_HOST = settings.DEV_MAIL_SMTP_HOST
    settings.SMTP_PORT = settings.DEV_MAIL_SMTP_PORT
    settings.SMTP_USE_TLS = False
    settings.SMTP_USERNAME = ""
    settings.SMTP_PASSWORD = ""
    logger.info(
        "Email backend routed to embedded mail catcher %s:%s",
        settings.SMTP_HOST,
        settings.SMTP_PORT,
    )


def start_dev_mail_server() -> bool:
    """Start SMTP + web inbox. Returns True if started (or already running)."""
    global _controller, _httpd, _http_thread, _started

    if _started:
        return True

    from app.core.config import settings

    smtp_host = settings.DEV_MAIL_SMTP_HOST
    smtp_port = settings.DEV_MAIL_SMTP_PORT
    web_host = settings.DEV_MAIL_WEB_HOST
    web_port = settings.DEV_MAIL_WEB_PORT

    try:
        from aiosmtpd.controller import Controller
    except ImportError:
        logger.warning("aiosmtpd is not installed; skip embedded mail catcher")
        return False

    MAIL_DIR.mkdir(parents=True, exist_ok=True)

    if not _port_free(smtp_host, smtp_port):
        logger.warning(
            "Dev mail SMTP port %s:%s already in use; assuming catcher is running",
            smtp_host,
            smtp_port,
        )
        wire_email_to_dev_mail()
        _started = True
        return True

    try:
        _controller = Controller(CaptureHandler(), hostname=smtp_host, port=smtp_port)
        _controller.start()
    except Exception:
        logger.exception("Failed to start embedded SMTP catcher")
        return False

    try:
        _httpd = ThreadingHTTPServer((web_host, web_port), InboxHandler)
        _http_thread = threading.Thread(target=_httpd.serve_forever, daemon=True)
        _http_thread.start()
    except OSError:
        logger.warning(
            "Dev mail web inbox port %s:%s unavailable; SMTP catcher is still running",
            web_host,
            web_port,
        )
        _httpd = None

    wire_email_to_dev_mail()
    _started = True
    inbox = f"http://{web_host}:{web_port}"
    logger.info(
        "Embedded dev mail started smtp=%s:%s inbox=%s store=%s",
        smtp_host,
        smtp_port,
        inbox,
        MAIL_DIR,
    )
    return True


def stop_dev_mail_server() -> None:
    global _controller, _httpd, _http_thread, _started

    if _httpd is not None:
        try:
            _httpd.shutdown()
            _httpd.server_close()
        except Exception:
            logger.exception("Error shutting down dev mail web inbox")
        _httpd = None
        _http_thread = None

    if _controller is not None:
        try:
            _controller.stop()
        except Exception:
            logger.exception("Error shutting down dev mail SMTP")
        _controller = None

    _started = False
