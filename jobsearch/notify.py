"""Email delivery. Two transports, chosen by which env vars are set:

  Resend (HTTPS REST, simplest):  RESEND_API_KEY [, RESEND_FROM]
  SMTP   (e.g. Gmail app pwd):    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS [, SMTP_FROM]

Returns (ok: bool, detail: str). Never raises into the caller.
"""
from __future__ import annotations

import json
import os
import smtplib
import ssl
import sys
import urllib.error
import urllib.request
from email.message import EmailMessage


def _log(msg: str) -> None:
    print(f"[notify] {msg}", file=sys.stderr)


def _send_resend(to: str, subject: str, html_body: str) -> tuple[bool, str]:
    key = os.environ["RESEND_API_KEY"]
    sender = os.environ.get("RESEND_FROM", "onboarding@resend.dev")
    payload = json.dumps({
        "from": sender, "to": [to], "subject": subject, "html": html_body,
    }).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails", data=payload, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    ctx = ssl.create_default_context()
    bundle = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
    if bundle and os.path.exists(bundle):
        ctx.load_verify_locations(bundle)
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            return (r.status < 400, f"resend HTTP {r.status}")
    except urllib.error.HTTPError as exc:
        # Resend explains 4xx in the body (e.g. the free-tier "you can only send
        # to your own verified address" restriction) — surface it, don't hide it.
        body = exc.read().decode("utf-8", "replace")[:300]
        return (False, f"resend HTTP {exc.code}: {body}")
    except Exception as exc:  # noqa: BLE001
        return (False, f"resend error: {exc}")


def _send_smtp(to: str, subject: str, html_body: str) -> tuple[bool, str]:
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    pwd = os.environ["SMTP_PASS"]
    sender = os.environ.get("SMTP_FROM", user)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content("This report is best viewed as HTML.")
    msg.add_alternative(html_body, subtype="html")
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=30) as s:
                s.login(user, pwd)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(user, pwd)
                s.send_message(msg)
        return (True, f"smtp {host}:{port} ok")
    except Exception as exc:  # noqa: BLE001
        return (False, f"smtp error: {exc}")


def send_email(to: str, subject: str, html_body: str) -> tuple[bool, str]:
    """Try each configured transport in order (Resend, then SMTP); return on the
    first success. If Resend is misconfigured but SMTP is set, delivery still
    goes through."""
    transports = []
    if os.environ.get("RESEND_API_KEY"):
        transports.append(("resend", _send_resend))
    if os.environ.get("SMTP_HOST"):
        transports.append(("smtp", _send_smtp))
    if not transports:
        _log("No email transport configured (set RESEND_API_KEY or SMTP_*). Skipping send.")
        return (False, "no transport configured")

    last = (False, "")
    for name, fn in transports:
        ok, detail = fn(to, subject, html_body)
        _log(detail)
        if ok:
            return (True, detail)
        last = (ok, detail)
    return last
