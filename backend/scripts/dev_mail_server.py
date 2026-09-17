"""Standalone launcher for the FinPay local mail catcher.

Prefer starting the backend — the catcher starts automatically with the API
in development. Use this script only if you need the inbox without uvicorn:

  python scripts/dev_mail_server.py
  python scripts/dev_mail_server.py --open
"""

from __future__ import annotations

import argparse
import webbrowser
from http.server import ThreadingHTTPServer

from aiosmtpd.controller import Controller

from app.notifications.dev_mail import (
    CaptureHandler,
    InboxHandler,
    MAIL_DIR,
    wire_email_to_dev_mail,
)


def main():
    parser = argparse.ArgumentParser(description="FinPay local mail catcher")
    parser.add_argument("--smtp-host", default="127.0.0.1")
    parser.add_argument("--smtp-port", type=int, default=1025)
    parser.add_argument("--web-host", default="127.0.0.1")
    parser.add_argument("--web-port", type=int, default=1080)
    parser.add_argument("--open", action="store_true", help="Open inbox in browser")
    args = parser.parse_args()

    MAIL_DIR.mkdir(parents=True, exist_ok=True)
    controller = Controller(CaptureHandler(), hostname=args.smtp_host, port=args.smtp_port)
    controller.start()
    wire_email_to_dev_mail()

    httpd = ThreadingHTTPServer((args.web_host, args.web_port), InboxHandler)
    url = f"http://{args.web_host}:{args.web_port}"
    print("FinPay Dev Mail running (no Docker)")
    print(f"  SMTP  {args.smtp_host}:{args.smtp_port}")
    print(f"  Inbox {url}")
    print(f"  Store {MAIL_DIR}")
    print("Note: when you start the FinPay backend in development, this catcher")
    print("starts automatically — you usually do not need this script.")
    print("Press Ctrl+C to stop.")

    if args.open:
        webbrowser.open(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping…")
    finally:
        httpd.server_close()
        controller.stop()


if __name__ == "__main__":
    main()
