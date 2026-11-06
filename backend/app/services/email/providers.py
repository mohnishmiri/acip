"""Email transport providers.

* ``smtp``  -- any SMTP relay (Office 365 ``smtp.office365.com:587`` STARTTLS, SendGrid, an
              internal relay, or Mailpit locally). Credentials come from environment only.
* ``graph`` -- Microsoft Graph ``POST /users/{sender}/sendMail`` with an app registration that has
              the *Mail.Send* application permission (restrict it to the sender mailbox with an
              Exchange application access policy).
* ``disabled`` -- no email is sent; deliveries are recorded as skipped with the reason.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
import uuid
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

import httpx

from app.core.config import Settings, get_settings

log = logging.getLogger(__name__)


class EmailNotConfigured(Exception):
    pass


class EmailSendError(Exception):
    pass


@dataclass
class OutgoingEmail:
    to: list[str]
    subject: str
    html: str
    text: str
    headers: dict[str, str] = field(default_factory=dict)


class SmtpProvider:
    name = "smtp"

    def __init__(self, s: Settings):
        self.s = s

    def build(self, msg: OutgoingEmail) -> EmailMessage:
        s = self.s
        m = EmailMessage()
        m["From"] = formataddr((s.email_from_name, s.email_from_address))
        m["To"] = ", ".join(msg.to)
        m["Subject"] = msg.subject
        m["Date"] = formatdate(localtime=False, usegmt=True)
        domain = s.email_from_address.split("@")[-1] if "@" in s.email_from_address else "acip.local"
        m["Message-ID"] = make_msgid(domain=domain)
        if s.email_reply_to:
            m["Reply-To"] = s.email_reply_to
        m["Auto-Submitted"] = "auto-generated"  # RFC 3834: suppress auto-replies
        m["X-Auto-Response-Suppress"] = "All"  # Exchange / Outlook
        for k, v in msg.headers.items():
            m[k] = v
        m.set_content(msg.text)
        m.add_alternative(msg.html, subtype="html")
        return m

    def send(self, msg: OutgoingEmail) -> str:
        s = self.s
        m = self.build(msg)
        try:
            if s.smtp_security == "ssl":
                server: smtplib.SMTP = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds, context=ssl.create_default_context())
            else:
                server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds)
            with server:
                server.ehlo()
                if s.smtp_security == "starttls":
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                if s.smtp_username:
                    server.login(s.smtp_username, s.smtp_password.get_secret_value() if s.smtp_password else "")
                server.send_message(m)
        except (smtplib.SMTPException, OSError) as exc:
            raise EmailSendError(f"SMTP {s.smtp_host}:{s.smtp_port}: {exc}") from exc
        return str(m["Message-ID"])


class GraphProvider:
    name = "graph"
    SCOPE = "https://graph.microsoft.com/.default"

    def __init__(self, s: Settings):
        if not s.graph_mail_sender:
            raise EmailNotConfigured("GRAPH_MAIL_SENDER is required for EMAIL_PROVIDER=graph")
        self.s = s

    def _token(self) -> str:
        from azure.identity import ClientSecretCredential

        s = self.s
        if s.graph_mail_client_id and s.graph_mail_client_secret:
            cred = ClientSecretCredential(s.graph_mail_tenant_id or s.azure_tenant_id, s.graph_mail_client_id, s.graph_mail_client_secret.get_secret_value())
        else:
            from app.integrations.azure_auth.credentials import get_credential

            cred = get_credential()
        return cred.get_token(self.SCOPE).token

    def send(self, msg: OutgoingEmail) -> str:
        s = self.s
        body = {
            "message": {
                "subject": msg.subject,
                "body": {"contentType": "HTML", "content": msg.html},
                "from": {"emailAddress": {"address": s.graph_mail_sender, "name": s.email_from_name}},
                "toRecipients": [{"emailAddress": {"address": a}} for a in msg.to],
                "replyTo": [{"emailAddress": {"address": s.email_reply_to}}] if s.email_reply_to else [],
                "internetMessageHeaders": [{"name": f"X-{k}" if not k.lower().startswith("x-") else k, "value": v} for k, v in msg.headers.items()],
            },
            "saveToSentItems": False,
        }
        if not body["message"]["internetMessageHeaders"]:
            body["message"].pop("internetMessageHeaders")
        try:
            r = httpx.post(f"https://graph.microsoft.com/v1.0/users/{s.graph_mail_sender}/sendMail", json=body,
                           headers={"Authorization": f"Bearer {self._token()}"}, timeout=30)
        except httpx.HTTPError as exc:
            raise EmailSendError(f"Microsoft Graph: {exc}") from exc
        if r.status_code != 202:
            raise EmailSendError(f"Microsoft Graph sendMail returned {r.status_code}: {r.text[:300]}")
        return r.headers.get("request-id") or str(uuid.uuid4())


def get_provider(s: Settings | None = None):
    s = s or get_settings()
    if s.email_provider == "smtp":
        return SmtpProvider(s)
    if s.email_provider == "graph":
        return GraphProvider(s)
    raise EmailNotConfigured("Email delivery is disabled (EMAIL_PROVIDER=disabled).")


def describe(s: Settings | None = None) -> dict:
    """Non-secret configuration summary for the UI."""
    s = s or get_settings()
    return {
        "provider": s.email_provider,
        "enabled": s.email_provider != "disabled",
        "from_address": s.email_from_address,
        "from_name": s.email_from_name,
        "reply_to": s.email_reply_to,
        "smtp_host": s.smtp_host if s.email_provider == "smtp" else None,
        "smtp_port": s.smtp_port if s.email_provider == "smtp" else None,
        "smtp_security": s.smtp_security if s.email_provider == "smtp" else None,
        "smtp_auth": bool(s.smtp_username) if s.email_provider == "smtp" else None,
        "graph_sender": s.graph_mail_sender if s.email_provider == "graph" else None,
        "public_url": s.app_public_url,
        "local_catcher": s.email_provider == "smtp" and s.smtp_host in ("mailpit", "localhost") and s.smtp_port == 1025,
    }
