"""Create one local test sales account for every region and sales tier."""

from __future__ import annotations

import os

from psycopg import connect

from ltc.modules.iam.infrastructure.passwords import Argon2PasswordVerifier
from ltc.platform.config import get_settings


DEFAULT_PASSWORD = "123456"

REGIONS = (
    ("EA", "东亚"),
    ("EU", "欧洲"),
    ("ME", "中东"),
    ("NA", "北美"),
    ("OTHER", "其他地区"),
    ("SEA", "东南亚"),
)

TIERS = (
    ("MA", 10),
    ("SA", 15),
    ("A", 20),
)


def main() -> None:
    if os.getenv("LTC_ENV", "local") == "production":
        raise SystemExit("regional test-user bootstrap is disabled in production")

    settings = get_settings()
    hasher = Argon2PasswordVerifier()
    created: list[str] = []
    existing: list[str] = []
    with connect(settings.database_dsn) as connection:
        for region_code, region_label in REGIONS:
            for sales_tier, capacity_limit in TIERS:
                username = f"sales.{region_code.lower()}.{sales_tier.lower()}"
                row = connection.execute(
                    """
                    INSERT INTO ltc.user_account (
                        username, password_hash, display_name, email,
                        account_type, sales_tier, region_code, capacity_limit
                    )
                    VALUES (%s, %s, %s, %s, 'sales', %s, %s, %s)
                    ON CONFLICT (lower(username)) DO NOTHING
                    RETURNING username
                    """,
                    (
                        username,
                        hasher.hash(DEFAULT_PASSWORD),
                        f"{region_label} {sales_tier} 测试销售",
                        f"{username}@ltc.test",
                        sales_tier,
                        region_code,
                        capacity_limit,
                    ),
                ).fetchone()
                (created if row else existing).append(username)
        connection.commit()

    print(f"Regional sales users ready: created={len(created)}, existing={len(existing)}")
    for username in created + existing:
        print(username)


if __name__ == "__main__":
    main()
