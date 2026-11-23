from __future__ import annotations

import argparse

from ltc.modules.customer_operation.application.inbound_mail_service import ImapInboundMailClient, InboundMailProcessor
from ltc.modules.customer_operation.infrastructure.mailbox_monitor_store import list_enabled_mailbox_monitors


def run_backfill(*, limit: int | None = None) -> dict[str, int]:
    processed = 0
    mailboxes = 0
    seen_addresses: set[str] = set()
    for monitor in list_enabled_mailbox_monitors(include_secret=True):
        address = str(monitor.get("username") or "").strip().lower()
        if not address or address in seen_addresses:
            continue
        seen_addresses.add(address)
        password = str(monitor.get("secretValue") or "")
        if not password:
            continue
        fetched = ImapInboundMailClient(
            host=str(monitor.get("host") or ""),
            port=int(monitor.get("port") or 993),
            username=address,
            password=password,
            mailbox=str(monitor.get("mailboxName") or "INBOX"),
        ).fetch_history(limit=limit)
        processor = InboundMailProcessor(sales_user_id=str(monitor.get("salesUserId") or ""))
        for email_item in fetched.emails:
            processor.process_emails([email_item])
            processed += 1
        mailboxes += 1
    return {"mailboxes": mailboxes, "processed": processed}


def main() -> int:
    parser = argparse.ArgumentParser(description="Import existing IMAP messages through the inbound-email pipeline.")
    parser.add_argument("--limit", type=int, default=None, help="Only inspect the newest N messages per unique mailbox.")
    args = parser.parse_args()
    print(run_backfill(limit=args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
