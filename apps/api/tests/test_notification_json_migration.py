import unittest

from ltc.modules.customer_operation.infrastructure.notification_migration import notification_update_values


def test_notification_update_values_preserves_read_state() -> None:
    values = notification_update_values({
        'emailId': 'email-1',
        'salesUserId': 'sales-1',
        'createdAt': '2026-08-03T02:15:31+00:00',
        'updatedAt': '2026-08-03T02:20:00+00:00',
        'read': True,
    })

    assert values['email_id'] == 'email-1'
    assert values['sales_user_id'] == 'sales-1'
    assert values['created_at'].isoformat() == '2026-08-03T02:15:31+00:00'
    assert values['read_at'].isoformat() == '2026-08-03T02:20:00+00:00'


def test_notification_update_values_rejects_missing_database_keys() -> None:
    assert notification_update_values({'read': False}) is None


def load_tests(loader, tests, pattern):
    del loader, tests, pattern
    return unittest.TestSuite([
        unittest.FunctionTestCase(test_notification_update_values_preserves_read_state),
        unittest.FunctionTestCase(test_notification_update_values_rejects_missing_database_keys),
    ])
