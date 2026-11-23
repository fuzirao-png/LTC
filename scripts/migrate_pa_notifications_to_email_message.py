from __future__ import annotations

import json
from pathlib import Path

from pg8000 import dbapi

from ltc.modules.customer_operation.application.pa_notification_service import NOTIFICATION_FILE
from ltc.modules.customer_operation.infrastructure.legacy_file_store import LegacyFileStore
from ltc.modules.customer_operation.infrastructure.notification_migration import notification_update_values
from ltc.platform.config import get_settings


def migrate(path: Path | None = None) -> dict[str, int]:
    notification_path = path or (LegacyFileStore().data_dir / NOTIFICATION_FILE)
    if not notification_path.exists():
        return {'scanned': 0, 'migrated': 0, 'skipped': 0}
    data = json.loads(notification_path.read_text(encoding='utf-8-sig') or '[]')
    items = data if isinstance(data, list) else []
    settings = get_settings()
    migrated = 0
    skipped = 0
    with dbapi.connect(
        user=settings.db_user, host=settings.db_host, database=settings.db_name,
        port=settings.db_port, password=settings.db_password, timeout=30,
    ) as conn:
        cur = conn.cursor()
        try:
            for item in items:
                values = notification_update_values(item) if isinstance(item, dict) else None
                if values is None:
                    skipped += 1
                    continue
                cur.execute(
                    """
                    UPDATE ltc.email_message
                    SET notification_created_at = COALESCE(notification_created_at, %s),
                        notification_read_at = COALESCE(notification_read_at, %s)
                    WHERE email_id = %s
                      AND sales_user_id = %s
                      AND direction = 'inbound'
                    RETURNING email_id
                    """,
                    (values['created_at'], values['read_at'], values['email_id'], values['sales_user_id']),
                )
                if cur.fetchone() is None:
                    skipped += 1
                else:
                    migrated += 1
            conn.commit()
        finally:
            cur.close()
    return {'scanned': len(items), 'migrated': migrated, 'skipped': skipped}


def main() -> None:
    result = migrate()
    print(
        'Notification migration complete: '
        f"scanned={result['scanned']} migrated={result['migrated']} skipped={result['skipped']}"
    )


if __name__ == '__main__':
    main()
