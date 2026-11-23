import psycopg

from ltc.platform.config import get_settings


def test_email_message_has_notification_columns_and_index() -> None:
    settings = get_settings()
    with psycopg.connect(settings.database_dsn) as connection:
        columns = {
            row[0]
            for row in connection.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'ltc'
                  AND table_name = 'email_message'
                  AND column_name IN (
                      'notification_created_at',
                      'notification_read_at',
                      'notification_dismissed_at'
                  )
                """
            ).fetchall()
        }
        indexes = {
            row[0]
            for row in connection.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'ltc' AND tablename = 'email_message'
                """
            ).fetchall()
        }

    assert columns == {
        'notification_created_at',
        'notification_read_at',
        'notification_dismissed_at',
    }
    assert 'ix_email_message_sales_notification' in indexes
