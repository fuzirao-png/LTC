from __future__ import annotations

import argparse
import os

import psycopg

from ltc.modules.customer_operation.infrastructure.mail_credential_cipher import MailCredentialCipher
from ltc.modules.iam.infrastructure.passwords import Argon2PasswordVerifier
from ltc.platform.config import get_settings


def _upsert_sales_user(connection: psycopg.Connection, *, username: str, display_name: str, email: str, region: str) -> str:
    password_hash = Argon2PasswordVerifier().hash(os.getenv("LTC_LOCAL_SALES_LOGIN_PASSWORD", "123456"))
    row = connection.execute(
        """
        INSERT INTO ltc.user_account (
            username, password_hash, display_name, email, account_type,
            sales_tier, region_code, capacity_limit, status
        ) VALUES (%s, %s, %s, %s, 'sales', 'MA', %s, 100, 'active')
        ON CONFLICT (lower(username)) DO UPDATE SET
            display_name = EXCLUDED.display_name,
            email = EXCLUDED.email,
            account_type = 'sales',
            sales_tier = 'MA',
            region_code = EXCLUDED.region_code,
            capacity_limit = COALESCE(ltc.user_account.capacity_limit, 100),
            status = 'active'
        RETURNING user_id
        """,
        (username, password_hash, display_name, email, region),
    ).fetchone()
    return str(row[0])


def _bind_mailbox(connection: psycopg.Connection, *, user_id: str, email: str, password: str) -> None:
    if not password:
        raise RuntimeError(f"Mailbox password is missing for {email}.")
    encrypted_password = MailCredentialCipher().encrypt(password)
    connection.execute(
        """
        INSERT INTO ltc.user_mailbox (
            user_id, email_address, smtp_host, smtp_port, smtp_use_ssl,
            imap_host, imap_port, imap_use_ssl, mailbox_name,
            encrypted_password, enabled, poll_seconds
        ) VALUES (%s, %s, 'smtp.exmail.qq.com', 465, true,
                  'imap.exmail.qq.com', 993, true, 'INBOX', %s, true, 60)
        ON CONFLICT (user_id) DO UPDATE SET
            email_address = EXCLUDED.email_address,
            smtp_host = EXCLUDED.smtp_host,
            smtp_port = EXCLUDED.smtp_port,
            smtp_use_ssl = EXCLUDED.smtp_use_ssl,
            imap_host = EXCLUDED.imap_host,
            imap_port = EXCLUDED.imap_port,
            imap_use_ssl = EXCLUDED.imap_use_ssl,
            mailbox_name = EXCLUDED.mailbox_name,
            encrypted_password = EXCLUDED.encrypted_password,
            enabled = true,
            updated_at = now()
        """,
        (user_id, email, encrypted_password),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--users-only", action="store_true")
    parser.add_argument("--mailbox", choices=("all", "li", "zong"), default="all")
    args = parser.parse_args()
    settings = get_settings()
    with psycopg.connect(settings.database_dsn) as connection:
        li_user_id = _upsert_sales_user(
            connection,
            username="li.ming",
            display_name="Li Ming",
            email="liming@ltc.test",
            region="EA",
        )
        zong_user_id = _upsert_sales_user(
            connection,
            username="zong.lin",
            display_name="Zong Lin",
            email="zong.lin@ltc.test",
            region="NA",
        )
        if not args.users_only and args.mailbox in {"all", "li"}:
            _bind_mailbox(
                connection,
                user_id=li_user_id,
                email="global.marketing@51tgt.com",
                password=os.getenv("LTC_MAILBOX_LI_PASSWORD", settings.smtp_password),
            )
        if not args.users_only and args.mailbox in {"all", "zong"}:
            _bind_mailbox(
                connection,
                user_id=zong_user_id,
                email="zonglin.yang@51tgt.com",
                password=os.getenv("LTC_MAILBOX_ZONG_PASSWORD", ""),
            )
        connection.commit()
    print("Local sales users and requested mailbox bindings are configured.")


if __name__ == "__main__":
    main()
