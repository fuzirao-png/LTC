"""Resolve the enabled operational mailbox owned by a user."""

from __future__ import annotations

import logging
from contextlib import closing
import psycopg
from psycopg.rows import dict_row

from ltc.platform.config import get_settings
from ltc.modules.customer_operation.infrastructure.mail_credential_cipher import MailCredentialCipher

_logger = logging.getLogger(__name__)


def resolve_user_email(user_id: str) -> dict[str, object]:
    """Return a user's mailbox config without cross-user/global fallback."""
    settings = get_settings()
    if not user_id:
        raise RuntimeError("Authenticated sales user is required for email delivery.")

    try:
        with closing(psycopg.connect(settings.database_dsn)) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT email_address, smtp_host, smtp_port, smtp_use_ssl,
                           imap_host, imap_port, imap_use_ssl, mailbox_name,
                           encrypted_password
                    FROM ltc.user_mailbox
                    WHERE user_id = %s AND enabled = true
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
            if not row:
                raise RuntimeError("No enabled mailbox is bound to the current sales user.")
            password = MailCredentialCipher().decrypt(str(row["encrypted_password"]))
            return {
                "mail_from": str(row["email_address"]),
                "smtp_username": str(row["email_address"]),
                "smtp_password": password,
                "smtp_host": str(row["smtp_host"]),
                "smtp_port": int(row["smtp_port"]),
                "smtp_use_ssl": bool(row["smtp_use_ssl"]),
                "imap_host": str(row["imap_host"]),
                "imap_port": int(row["imap_port"]),
                "imap_use_ssl": bool(row["imap_use_ssl"]),
                "mailbox_name": str(row["mailbox_name"]),
            }
    except psycopg.Error as exc:
        _logger.error("Cannot resolve mailbox for user %s: %s", user_id[:12], exc)
        raise RuntimeError("Cannot resolve mailbox for the current sales user.") from exc
