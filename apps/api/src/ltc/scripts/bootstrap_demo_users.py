"""Create idempotent local development accounts."""

from __future__ import annotations

import os

from psycopg import connect

from ltc.modules.iam.infrastructure.passwords import Argon2PasswordVerifier
from ltc.platform.config import get_settings


DEMO_USERS = (
    ("strategic.local", "123456", "Strategic Admin", "strategic.local@ltc.test", "strategic", None, None, None),
    ("lin.wei", "123456", "Lin Wei", "lin.wei@ltc.test", "sales", "MA", "EA", 10),
)


def main() -> None:
    if os.getenv("LTC_ENV", "local") == "production":
        raise SystemExit("bootstrap_demo_users is disabled in production")
    hasher = Argon2PasswordVerifier()
    settings = get_settings()
    with connect(settings.database_dsn) as connection:
        for username, password, display_name, email, account_type, sales_tier, region_code, capacity_limit in DEMO_USERS:
            connection.execute(
                """INSERT INTO ltc.user_account
                   (username, password_hash, display_name, email, account_type, sales_tier, region_code, capacity_limit)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (lower(username)) DO NOTHING""",
                (username, hasher.hash(password), display_name, email, account_type, sales_tier, region_code, capacity_limit),
            )
        connection.commit()
    print("Bootstrap users are ready: strategic.local and lin.wei")


if __name__ == "__main__":
    main()
