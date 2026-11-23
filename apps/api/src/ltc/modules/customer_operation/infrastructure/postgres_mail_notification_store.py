from __future__ import annotations

from contextlib import closing
from datetime import datetime
from typing import Any

from pg8000 import dbapi

from ltc.platform.config import get_settings


class PostgresMailNotificationStore:
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

    @staticmethod
    def _iso(value: Any) -> str:
        return value.isoformat() if isinstance(value, datetime) else str(value or '')

    @classmethod
    def _map_notification(cls, row: tuple[Any, ...]) -> dict[str, Any]:
        email_id, company_id, sales_user_id, subject, body, from_address, to_address, message_id, created_at, read_at, company_name = row
        body_text = str(body or '')
        return {
            'id': str(email_id),
            'role': 'sales',
            'type': 'email',
            'eventType': 'imap.received',
            'messageId': str(message_id or ''),
            'companyId': str(company_id),
            'emailId': str(email_id),
            'salesUserId': str(sales_user_id),
            'priority': 'high',
            'title': '收到邮件提醒',
            'body': body_text[:240],
            'customerName': str(company_name or ''),
            'subject': str(subject or ''),
            'from': str(from_address or ''),
            'to': str(to_address or ''),
            'notificationTarget': {
                'companyId': str(company_id),
                'emailId': str(email_id),
                'messageId': str(message_id or ''),
            },
            'read': read_at is not None,
            'createdAt': cls._iso(created_at),
            'updatedAt': cls._iso(read_at or created_at),
        }

    @classmethod
    def _map_detail(cls, row: tuple[Any, ...]) -> dict[str, Any]:
        email_id, message_id, from_address, to_address, subject, body, received_at, company_id, sales_user_id = row
        return {
            'notificationId': str(email_id),
            'messageId': str(message_id or ''),
            'from': str(from_address or ''),
            'to': str(to_address or ''),
            'subject': str(subject or ''),
            'bodyPreview': str(body or '')[:240],
            'bodyText': str(body or ''),
            'receivedAt': cls._iso(received_at),
            'companyId': str(company_id),
            'salesUserId': str(sales_user_id),
            'raw': {
                'message_id': str(message_id or ''),
                'from': str(from_address or ''),
                'to': str(to_address or ''),
                'subject': str(subject or ''),
            },
        }

    def list_notifications(self, *, role: str = 'sales', unread_only: bool = True, user_id: str = '', limit: int = 50) -> list[dict[str, Any]]:
        if role != 'sales' or not user_id:
            return []
        unread_filter = 'AND e.notification_read_at IS NULL' if unread_only else ''
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    f"""
                    SELECT e.email_id, e.company_id, e.sales_user_id, e.subject, e.body_text,
                           e.from_address, COALESCE(e.delivered_to_address, e.intended_to_address),
                           e.message_id_header, e.notification_created_at, e.notification_read_at,
                           c.company_name
                    FROM ltc.email_message e
                    JOIN ltc.company c ON c.company_id = e.company_id
                    JOIN ltc.user_mailbox um ON um.user_id = e.sales_user_id
                    WHERE e.direction = 'inbound'
                      AND (um.sync_initialized_at IS NULL OR e.notification_created_at > um.sync_initialized_at)
                      AND e.sales_user_id = %s
                      AND e.notification_created_at IS NOT NULL
                      AND e.notification_dismissed_at IS NULL
                      {unread_filter}
                    ORDER BY e.notification_created_at DESC, e.email_id DESC
                    LIMIT %s
                    """,
                    (user_id, limit),
                )
                return [self._map_notification(tuple(row)) for row in cur.fetchall()]
            finally:
                cur.close()

    def get_notification(self, notification_id: str, *, user_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    SELECT e.email_id, e.company_id, e.sales_user_id, e.subject, e.body_text,
                           e.from_address, COALESCE(e.delivered_to_address, e.intended_to_address),
                           e.message_id_header, e.notification_created_at, e.notification_read_at,
                           c.company_name
                    FROM ltc.email_message e
                    JOIN ltc.company c ON c.company_id = e.company_id
                    JOIN ltc.user_mailbox um ON um.user_id = e.sales_user_id
                    WHERE e.email_id = %s AND e.sales_user_id = %s
                      AND (um.sync_initialized_at IS NULL OR e.notification_created_at > um.sync_initialized_at)
                      AND e.direction = 'inbound'
                      AND e.notification_created_at IS NOT NULL
                      AND e.notification_dismissed_at IS NULL
                    """,
                    (notification_id, user_id),
                )
                row = cur.fetchone()
                return self._map_notification(tuple(row)) if row else None
            finally:
                cur.close()

    def get_detail(self, notification_id: str, *, user_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    SELECT e.email_id, e.message_id_header, e.from_address,
                           COALESCE(e.delivered_to_address, e.intended_to_address),
                           e.subject, e.body_text, COALESCE(e.received_at, e.created_at),
                           e.company_id, e.sales_user_id
                    FROM ltc.email_message e
                    JOIN ltc.user_mailbox um ON um.user_id = e.sales_user_id
                    WHERE e.email_id = %s AND e.sales_user_id = %s
                      AND (um.sync_initialized_at IS NULL OR e.notification_created_at > um.sync_initialized_at)
                      AND e.direction = 'inbound'
                      AND e.notification_created_at IS NOT NULL
                      AND e.notification_dismissed_at IS NULL
                    """,
                    (notification_id, user_id),
                )
                row = cur.fetchone()
                return self._map_detail(tuple(row)) if row else None
            finally:
                cur.close()

    def mark_read(self, notification_id: str, *, user_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    UPDATE ltc.email_message e
                    SET notification_read_at = COALESCE(e.notification_read_at, now())
                    FROM ltc.user_mailbox um
                    WHERE e.email_id = %s AND e.sales_user_id = %s
                      AND um.user_id = e.sales_user_id
                      AND (um.sync_initialized_at IS NULL OR e.notification_created_at > um.sync_initialized_at)
                      AND direction = 'inbound'
                      AND notification_created_at IS NOT NULL
                      AND notification_dismissed_at IS NULL
                    RETURNING email_id
                    """,
                    (notification_id, user_id),
                )
                row = cur.fetchone()
                conn.commit()
            finally:
                cur.close()
        if row is None:
            return None
        return self.get_notification(notification_id, user_id=user_id)
