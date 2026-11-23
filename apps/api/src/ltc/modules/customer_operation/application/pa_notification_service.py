from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from ltc.modules.customer_operation.infrastructure.postgres_mail_notification_store import (
    PostgresMailNotificationStore,
)


NOTIFICATION_FILE = 'pa-notifications.json'


class PaNotificationService:
    def __init__(self, data_dir: Path | None = None, store: Any | None = None) -> None:
        self.data_dir = data_dir
        self.store = store or (None if data_dir is not None else PostgresMailNotificationStore())

    @property
    def file_mode(self) -> bool:
        return self.data_dir is not None

    def _read_items(self) -> list[dict[str, Any]]:
        if not self.file_mode:
            raise RuntimeError('JSON notification storage is only available with an explicit data_dir.')
        path = self.data_dir / NOTIFICATION_FILE
        if not path.exists():
            return []
        import json
        data = json.loads(path.read_text(encoding='utf-8-sig') or '[]')
        return data if isinstance(data, list) else []

    def _write_items(self, items: list[dict[str, Any]]) -> None:
        if not self.file_mode:
            raise RuntimeError('JSON notification storage is only available with an explicit data_dir.')
        self.data_dir.mkdir(parents=True, exist_ok=True)
        import json
        (self.data_dir / NOTIFICATION_FILE).write_text(
            json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8'
        )

    def create_from_event(self, event: dict[str, Any], role: str = 'sales') -> dict[str, Any]:
        if not self.file_mode:
            email_id = str(event.get('emailId') or event.get('email_id') or '')
            user_id = str(event.get('salesUserId') or event.get('sales_user_id') or '')
            item = self.store.get_notification(email_id, user_id=user_id) if email_id and user_id else None
            return item or {}

        items = self._read_items()
        event_type = str(event.get('eventType') or 'unknown')
        message_id = str(event.get('messageId') or '')
        duplicate = next((item for item in items if item.get('eventType') == event_type and item.get('messageId') == message_id and message_id), None)
        company_id = str(event.get('companyId') or event.get('company_id') or '')
        email_id = str(event.get('emailId') or event.get('email_id') or '')
        sales_user_id = str(event.get('salesUserId') or event.get('sales_user_id') or '')
        if duplicate is not None:
            duplicate.update({'companyId': company_id or duplicate.get('companyId', ''), 'emailId': email_id or duplicate.get('emailId', ''), 'salesUserId': sales_user_id or duplicate.get('salesUserId', '')})
            duplicate['notificationTarget'] = {'companyId': duplicate['companyId'], 'emailId': duplicate['emailId'], 'messageId': message_id}
            self._write_items(items)
            return duplicate
        now = datetime.now(timezone.utc).isoformat()
        notification = {
            'id': str(uuid4()), 'role': role, 'type': 'email', 'eventType': event_type,
            'messageId': message_id, 'companyId': company_id, 'emailId': email_id,
            'salesUserId': sales_user_id, 'priority': str(event.get('priority') or 'normal'),
            'title': str(event.get('notificationTitle') or '收到邮件提醒'),
            'body': str(event.get('notificationBody') or ''),
            'customerName': str(event.get('customerName') or ''),
            'subject': str(event.get('subject') or ''), 'from': str(event.get('from') or ''),
            'to': str(event.get('to') or ''),
            'notificationTarget': {'companyId': company_id, 'emailId': email_id, 'messageId': message_id},
            'read': False, 'createdAt': str(event.get('createdAt') or now), 'updatedAt': now,
        }
        items.insert(0, notification)
        self._write_items(items[:500])
        return notification

    def list_notifications(self, role: str = 'sales', unread_only: bool = True, user_id: str = '') -> list[dict[str, Any]]:
        if not self.file_mode:
            return self.store.list_notifications(role=role, unread_only=unread_only, user_id=user_id)
        items = [item for item in self._read_items() if item.get('role') == role]
        if user_id:
            items = [item for item in items if str(item.get('salesUserId') or '') == user_id]
        if unread_only:
            items = [item for item in items if not item.get('read')]
        return items[:50]

    def get_notification(self, notification_id: str, *, user_id: str) -> dict[str, Any] | None:
        if not self.file_mode:
            return self.store.get_notification(notification_id, user_id=user_id)
        return next((item for item in self.list_notifications(unread_only=False, user_id=user_id) if item.get('id') == notification_id), None)

    def get_detail(self, notification_id: str, *, user_id: str) -> dict[str, Any] | None:
        if not self.file_mode:
            return self.store.get_detail(notification_id, user_id=user_id)
        return None

    def mark_read(self, notification_id: str, *, user_id: str = '') -> dict[str, Any]:
        if not self.file_mode:
            item = self.store.mark_read(notification_id, user_id=user_id)
            if item is None:
                raise KeyError(notification_id)
            return item
        items = self._read_items()
        for item in items:
            if item.get('id') == notification_id and (not user_id or str(item.get('salesUserId') or '') == user_id):
                item['read'] = True
                item['updatedAt'] = datetime.now(timezone.utc).isoformat()
                self._write_items(items)
                return item
        raise KeyError(notification_id)
