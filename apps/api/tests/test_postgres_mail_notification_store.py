from datetime import datetime, timezone

from ltc.modules.customer_operation.infrastructure.postgres_mail_notification_store import (
    PostgresMailNotificationStore,
)


def test_notification_row_maps_to_existing_api_contract() -> None:
    created_at = datetime(2026, 8, 3, 2, 15, tzinfo=timezone.utc)
    item = PostgresMailNotificationStore._map_notification((
        'email-1', 'company-1', 'sales-1', '方案讨论', '方案没问题。',
        'buyer@example.com', 'sales@example.com', '<message-1>', created_at, None, 'Example Company',
    ))

    assert item['id'] == 'email-1'
    assert item['emailId'] == 'email-1'
    assert item['companyId'] == 'company-1'
    assert item['salesUserId'] == 'sales-1'
    assert item['read'] is False
    assert item['notificationTarget'] == {
        'companyId': 'company-1',
        'emailId': 'email-1',
        'messageId': '<message-1>',
    }
    assert item['subject'] == '方案讨论'


def test_notification_detail_maps_email_body() -> None:
    created_at = datetime(2026, 8, 3, 2, 15, tzinfo=timezone.utc)
    detail = PostgresMailNotificationStore._map_detail((
        'email-1', '<message-1>', 'buyer@example.com', 'sales@example.com',
        '方案讨论', '方案没问题。', created_at, 'company-1', 'sales-1',
    ))

    assert detail['notificationId'] == 'email-1'
    assert detail['bodyText'] == '方案没问题。'
    assert detail['raw']['message_id'] == '<message-1>'
