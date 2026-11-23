from __future__ import annotations

from contextlib import closing
from typing import Any

from pg8000 import dbapi

from ltc.platform.config import get_settings
from ltc.modules.customer_operation.infrastructure.mail_credential_cipher import MailCredentialCipher


def list_enabled_mailbox_monitors(*, include_secret: bool = False) -> list[dict[str, Any]]:
    settings = get_settings()
    if not all([settings.db_host, settings.db_name, settings.db_user, settings.db_password]):
        return []

    with closing(
        dbapi.connect(
            user=settings.db_user,
            host=settings.db_host,
            database=settings.db_name,
            port=settings.db_port,
            password=settings.db_password,
            timeout=30,
        )
    ) as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT user_mailbox_id, user_id, imap_host, imap_port,
                       email_address, encrypted_password, mailbox_name,
                       enabled, poll_seconds, last_polled_at, imap_uid_validity,
                       last_processed_uid, sync_initialized_at, last_poll_error,
                       created_at, updated_at
                FROM ltc.user_mailbox
                WHERE enabled = true
                ORDER BY created_at ASC
                """
            )
            rows = cur.fetchall() or []
        finally:
            cur.close()

    cipher = MailCredentialCipher() if include_secret and rows else None
    return [{
        "mailboxMonitorId": str(row[0]),
        "salesUserId": str(row[1]),
        "providerCode": "imap",
        "host": str(row[2]),
        "port": int(row[3]),
        "username": str(row[4]),
        **({"secretValue": cipher.decrypt(str(row[5]))} if cipher is not None else {}),
        "mailboxName": str(row[6]),
        "enabled": bool(row[7]),
        "pollSeconds": int(row[8]),
        "lastPolledAt": row[9].isoformat() if row[9] is not None else None,
        "imapUidValidity": int(row[10]) if row[10] is not None else None,
        "lastProcessedUid": int(row[11]) if row[11] is not None else None,
        "syncInitializedAt": row[12].isoformat() if row[12] is not None else None,
        "lastPollError": str(row[13]) if row[13] is not None else None,
        "createdAt": row[14].isoformat() if row[14] is not None else None,
        "updatedAt": row[15].isoformat() if row[15] is not None else None,
    } for row in rows]


class PostgresMailboxSyncStore:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _connect(self):
        return dbapi.connect(
            user=self.settings.db_user,
            host=self.settings.db_host,
            database=self.settings.db_name,
            port=self.settings.db_port,
            password=self.settings.db_password,
            timeout=30,
        )

    def initialize(self, mailbox_monitor_id: str, uid_validity: int, highest_uid: int) -> None:
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    UPDATE ltc.user_mailbox
                    SET imap_uid_validity = %s,
                        last_processed_uid = %s,
                        sync_initialized_at = now(),
                        last_polled_at = now(),
                        last_poll_error = NULL,
                        last_error = NULL,
                        updated_at = now()
                    WHERE user_mailbox_id = %s
                    """,
                    (uid_validity, highest_uid, mailbox_monitor_id),
                )
                conn.commit()
            finally:
                cur.close()

    def advance(self, mailbox_monitor_id: str, uid_validity: int, processed_uid: int) -> None:
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    UPDATE ltc.user_mailbox
                    SET imap_uid_validity = %s,
                        last_processed_uid = GREATEST(COALESCE(last_processed_uid, 0), %s),
                        last_polled_at = now(),
                        last_poll_error = NULL,
                        last_error = NULL,
                        updated_at = now()
                    WHERE user_mailbox_id = %s
                    """,
                    (uid_validity, processed_uid, mailbox_monitor_id),
                )
                conn.commit()
            finally:
                cur.close()

    def record_success(self, mailbox_monitor_id: str) -> None:
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    UPDATE ltc.user_mailbox
                    SET last_polled_at = now(), last_poll_error = NULL, last_error = NULL, updated_at = now()
                    WHERE user_mailbox_id = %s
                    """,
                    (mailbox_monitor_id,),
                )
                conn.commit()
            finally:
                cur.close()

    def record_error(self, mailbox_monitor_id: str, message: str) -> None:
        error_message = str(message or "")[:2000]
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    UPDATE ltc.user_mailbox
                    SET last_polled_at = now(), last_poll_error = %s, last_error = %s, updated_at = now()
                    WHERE user_mailbox_id = %s
                    """,
                    (error_message, error_message, mailbox_monitor_id),
                )
                conn.commit()
            finally:
                cur.close()


def upsert_default_mailbox_monitor() -> dict[str, Any] | None:
    settings = get_settings()
    if not all([settings.db_host, settings.db_name, settings.db_user, settings.db_password]):
        return None

    with closing(
        dbapi.connect(
            user=settings.db_user,
            host=settings.db_host,
            database=settings.db_name,
            port=settings.db_port,
            password=settings.db_password,
            timeout=30,
        )
    ) as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO ltc.mailbox_monitor (
                    provider_code,
                    host,
                    port,
                    username,
                    secret_env_var,
                    secret_value,
                    mailbox_name,
                    enabled,
                    poll_seconds
                )
                VALUES ('imap', %s, %s, %s, 'INBOUND_MAIL_PASSWORD', %s, %s, %s, %s)
                ON CONFLICT (provider_code, username, mailbox_name)
                DO UPDATE SET
                    host = EXCLUDED.host,
                    port = EXCLUDED.port,
                    secret_value = EXCLUDED.secret_value,
                    enabled = EXCLUDED.enabled,
                    poll_seconds = EXCLUDED.poll_seconds
                RETURNING mailbox_monitor_id
                """,
                (
                    settings.inbound_mail_host,
                    settings.inbound_mail_port,
                    settings.inbound_mail_username,
                    settings.inbound_mail_password or None,
                    settings.inbound_mail_mailbox,
                    settings.inbound_mail_enabled,
                    settings.inbound_mail_poll_seconds,
                ),
            )
            row = cur.fetchone()
            conn.commit()
            return {"mailboxMonitorId": str(row[0])} if row else None
        finally:
            cur.close()


def upsert_mailbox_monitor(
    *,
    provider_code: str,
    host: str,
    port: int,
    username: str,
    secret_env_var: str,
    secret_value: str | None = None,
    mailbox_name: str = "INBOX",
    enabled: bool = True,
    poll_seconds: int = 60,
) -> dict[str, Any] | None:
    settings = get_settings()
    if not all([settings.db_host, settings.db_name, settings.db_user, settings.db_password]):
        return None

    with closing(
        dbapi.connect(
            user=settings.db_user,
            host=settings.db_host,
            database=settings.db_name,
            port=settings.db_port,
            password=settings.db_password,
            timeout=30,
        )
    ) as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO ltc.mailbox_monitor (
                    provider_code,
                    host,
                    port,
                    username,
                    secret_env_var,
                    secret_value,
                    mailbox_name,
                    enabled,
                    poll_seconds
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (provider_code, username, mailbox_name)
                DO UPDATE SET
                    host = EXCLUDED.host,
                    port = EXCLUDED.port,
                    secret_env_var = EXCLUDED.secret_env_var,
                    secret_value = EXCLUDED.secret_value,
                    enabled = EXCLUDED.enabled,
                    poll_seconds = EXCLUDED.poll_seconds
                RETURNING mailbox_monitor_id
                """,
                (
                    provider_code,
                    host,
                    port,
                    username,
                    secret_env_var,
                    secret_value,
                    mailbox_name,
                    enabled,
                    poll_seconds,
                ),
            )
            row = cur.fetchone()
            conn.commit()
            return {"mailboxMonitorId": str(row[0])} if row else None
        finally:
            cur.close()


def update_mailbox_monitor(
    *,
    mailbox_monitor_id: str,
    host: str | None = None,
    port: int | None = None,
    secret_env_var: str | None = None,
    secret_value: str | None = None,
    mailbox_name: str | None = None,
    enabled: bool | None = None,
    poll_seconds: int | None = None,
) -> dict[str, Any] | None:
    settings = get_settings()
    if not all([settings.db_host, settings.db_name, settings.db_user, settings.db_password]):
        return None

    with closing(
        dbapi.connect(
            user=settings.db_user,
            host=settings.db_host,
            database=settings.db_name,
            port=settings.db_port,
            password=settings.db_password,
            timeout=30,
        )
    ) as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                UPDATE ltc.mailbox_monitor
                SET
                    host = COALESCE(%s, host),
                    port = COALESCE(%s, port),
                    secret_env_var = COALESCE(%s, secret_env_var),
                    secret_value = COALESCE(%s, secret_value),
                    mailbox_name = COALESCE(%s, mailbox_name),
                    enabled = COALESCE(%s, enabled),
                    poll_seconds = COALESCE(%s, poll_seconds)
                WHERE mailbox_monitor_id = %s
                RETURNING mailbox_monitor_id
                """,
                (
                    host,
                    port,
                    secret_env_var,
                    secret_value,
                    mailbox_name,
                    enabled,
                    poll_seconds,
                    mailbox_monitor_id,
                ),
            )
            row = cur.fetchone()
            conn.commit()
            return {"mailboxMonitorId": str(row[0])} if row else None
        finally:
            cur.close()



