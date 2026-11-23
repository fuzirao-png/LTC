from __future__ import annotations

import asyncio
import base64
import smtplib
from email.message import EmailMessage
from html import escape
from typing import Any
from uuid import uuid4

from ltc.platform.config import get_settings
from ltc.modules.customer_operation.infrastructure.user_email_resolver import resolve_user_email


class SmtpEmailClient:
    def __init__(self, user_id: str = "") -> None:
        self.settings = get_settings()
        self._user_id = user_id
        self._user_email: dict[str, object] | None = None

    def _email_config(self) -> dict[str, object]:
        if self._user_email is None:
            self._user_email = resolve_user_email(self._user_id)
        return self._user_email

    def _smtp_credentials(self) -> tuple[str, str]:
        email_cfg = self._email_config()
        username = str(email_cfg.get("smtp_username") or email_cfg.get("mail_from") or "")
        password = str(email_cfg.get("smtp_password") or "")
        if not username:
            raise RuntimeError("SMTP_USERNAME or MAIL_FROM is not configured.")
        if not password:
            raise RuntimeError("SMTP_PASSWORD or MAIL_API_KEY is not configured.")
        return username, password

    def _make_message(
        self,
        *,
        recipient_email: str,
        subject: str,
        body: str,
        attachments: list[dict[str, str]] | None = None,
    ) -> EmailMessage:
        message = EmailMessage()
        # Use per-user from address if available
        from_addr = str(self._email_config().get("mail_from") or "")
        message["From"] = from_addr
        message["To"] = recipient_email
        message["Subject"] = subject
        from_domain = str(from_addr).rsplit("@", 1)[-1].strip() if "@" in from_addr else "localhost"
        message["Message-ID"] = message.get("Message-ID") or f"<{uuid4()}@{from_domain}>"
        message.set_content(body)
        message.add_alternative(
            "<div style=\"font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.8;color:#111827;white-space:pre-wrap;\">"
            f"{escape(body)}"
            "</div>",
            subtype="html",
        )

        for item in attachments or []:
            filename = str(item.get("filename") or "attachment.bin")
            content_type = str(item.get("contentType") or "application/octet-stream")
            raw_content = str(item.get("content") or "")
            try:
                payload = base64.b64decode(raw_content)
            except Exception:
                payload = raw_content.encode("utf-8")
            maintype, _, subtype = content_type.partition("/")
            if not maintype or not subtype:
                maintype, subtype = "application", "octet-stream"
            message.add_attachment(payload, maintype=maintype, subtype=subtype, filename=filename)
        return message

    def _send_sync(
        self,
        *,
        recipient_email: str,
        subject: str,
        body: str,
        attachments: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        username, password = self._smtp_credentials()
        message = self._make_message(
            recipient_email=recipient_email,
            subject=subject,
            body=body,
            attachments=attachments,
        )

        email_cfg = self._email_config()
        host = str(email_cfg["smtp_host"])
        port = int(email_cfg["smtp_port"])
        if bool(email_cfg["smtp_use_ssl"]):
            with smtplib.SMTP_SSL(host, port, timeout=60) as client:
                client.login(username, password)
                refused = client.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=60) as client:
                client.ehlo()
                client.starttls()
                client.ehlo()
                client.login(username, password)
                refused = client.send_message(message)

        if refused:
            recipients = ", ".join(sorted(str(address) for address in refused))
            raise RuntimeError(f"SMTP refused recipient(s): {recipients}")

        return {
            "provider": "smtp",
            "messageId": message.get("Message-ID") or "",
            "deliveredTo": recipient_email,
            "mode": "direct",
            "smtpStatus": "submitted",
            "deliveryStatus": "unconfirmed",
            "deliveryConfirmed": False,
            "raw": {
                "host": host,
                "port": port,
            },
        }
    async def send(
        self,
        *,
        recipient_email: str,
        subject: str,
        body: str,
        attachments: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._send_sync,
            recipient_email=recipient_email,
            subject=subject,
            body=body,
            attachments=attachments,
        )

