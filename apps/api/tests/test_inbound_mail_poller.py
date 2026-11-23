from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from ltc.modules.customer_operation.application.inbound_mail_service import (
    ImapInboundMailClient,
    ImapMailboxFetchResult,
    InboundEmail,
    InboundMailPoller,
    parse_raw_email,
)


class _FakeClient:
    def __init__(self, result: ImapMailboxFetchResult | None = None) -> None:
        self.result = result or ImapMailboxFetchResult(
            uid_validity=1,
            highest_uid=1,
            emails=(
                InboundEmail(
                    "1", "<1@example.com>", "a@example.com", "sales@example.com",
                    "A", "A", "A", "2026-08-05T00:00:00+00:00",
                ),
            ),
        )
        self.calls: list[tuple[int | None, int | None]] = []

    def fetch_since(self, *, last_processed_uid: int | None, expected_uid_validity: int | None) -> ImapMailboxFetchResult:
        self.calls.append((last_processed_uid, expected_uid_validity))
        return self.result


class _LoopDetectingProcessor:
    def process_emails(self, emails: list[object]) -> list[str]:
        self.emails = emails
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return ["processed-off-loop"]
        raise AssertionError("synchronous mail processing ran on the API event loop")


class _FailingProcessor:
    def process_emails(self, emails: list[InboundEmail]) -> list[dict[str, str]]:
        raise RuntimeError("broken inbound message")


class _RecordingSyncStore:
    def __init__(self) -> None:
        self.initialized: list[tuple[str, int, int]] = []
        self.advanced: list[tuple[str, int, int]] = []
        self.successes: list[str] = []
        self.errors: list[tuple[str, str]] = []

    def initialize(self, mailbox_monitor_id: str, uid_validity: int, highest_uid: int) -> None:
        self.initialized.append((mailbox_monitor_id, uid_validity, highest_uid))

    def advance(self, mailbox_monitor_id: str, uid_validity: int, processed_uid: int) -> None:
        self.advanced.append((mailbox_monitor_id, uid_validity, processed_uid))

    def record_success(self, mailbox_monitor_id: str) -> None:
        self.successes.append(mailbox_monitor_id)

    def record_error(self, mailbox_monitor_id: str, message: str) -> None:
        self.errors.append((mailbox_monitor_id, message))


class _FakeImapSession:
    def __init__(self) -> None:
        self.login_args: tuple[str, str] | None = None
        self.authenticate_args: tuple[str, bytes] | None = None

    def login(self, username: str, password: str) -> None:
        self.login_args = username, password

    def authenticate(self, mechanism: str, callback) -> None:
        self.authenticate_args = mechanism, callback(b"")


class _FakeMailboxSession(_FakeImapSession):
    def __init__(self, *, uid_validity: int, all_uids: bytes, new_uids: bytes = b"") -> None:
        super().__init__()
        self.uid_validity = uid_validity
        self.all_uids = all_uids
        self.new_uids = new_uids
        self.uid_calls: list[tuple[object, ...]] = []
        self.select_args: tuple[str, bool] | None = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def _simple_command(self, command: str, payload: str):
        return "OK", [b""]

    def select(self, mailbox: str, readonly: bool = False):
        self.select_args = mailbox, readonly
        return "OK", [b"1"]

    def response(self, code: str):
        assert code == "UIDVALIDITY"
        return code, [str(self.uid_validity).encode("ascii")]

    def uid(self, *args):
        self.uid_calls.append(args)
        if args[:3] == ("search", None, "ALL"):
            return "OK", [self.all_uids]
        if args[0] == "search":
            return "OK", [self.new_uids]
        if args[0] == "fetch":
            uid = str(args[1])
            raw = (
                f"From: buyer{uid}@example.com\r\n"
                "To: sales@example.com\r\n"
                f"Message-ID: <{uid}@example.com>\r\n"
                f"Subject: Message {uid}\r\n\r\nBody"
            ).encode("ascii")
            return "OK", [(b"RFC822", raw)]
        raise AssertionError(args)


class InboundMailPollerTests(unittest.IsolatedAsyncioTestCase):
    def test_ascii_credentials_use_imap_login(self) -> None:
        client = ImapInboundMailClient(
            host="imap.example.com",
            port=993,
            username="sales@example.com",
            password="ascii-secret!",
        )
        session = _FakeImapSession()

        client._login(session)

        self.assertEqual(session.login_args, ("sales@example.com", "ascii-secret!"))
        self.assertIsNone(session.authenticate_args)

    def test_unicode_credentials_use_utf8_sasl_plain(self) -> None:
        client = ImapInboundMailClient(
            host="imap.example.com",
            port=993,
            username="sales@example.com",
            password="unicode-secret！",
        )
        session = _FakeImapSession()

        client._login(session)

        self.assertIsNone(session.login_args)
        self.assertEqual(
            session.authenticate_args,
            ("PLAIN", "\0sales@example.com\0unicode-secret！".encode("utf-8")),
        )

    def test_parse_raw_email_prefers_html_delivery_report_over_embedded_original_text(self) -> None:
        raw = (
            b"From: postmaster@51tgt.com\r\nTo: global.marketing@51tgt.com\r\n"
            b"Message-ID: <bounce@example.com>\r\nSubject: Bounce\r\n"
            b"Content-Type: multipart/alternative; boundary=x\r\n\r\n"
            b"--x\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nOriginal sales email only\r\n"
            b"--x\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
            b"<p>Delivery failed</p><p>Unable to send to buyer@example.com</p>"
            b"<p>550 5.4.1 Recipient address rejected: Access denied.</p>\r\n--x--\r\n"
        )
        parsed = parse_raw_email("50", raw)
        self.assertIn("buyer@example.com", parsed.body_text)
        self.assertIn("550 5.4.1", parsed.body_text)

    async def test_poll_once_runs_synchronous_processing_off_event_loop(self) -> None:
        poller = InboundMailPoller(
            client=_FakeClient(),
            processor=_LoopDetectingProcessor(),
            interval_seconds=60,
            mailbox_monitor_id="mailbox-1",
            uid_validity=1,
            last_processed_uid=0,
            sync_store=_RecordingSyncStore(),
        )

        result = await poller.poll_once()

        self.assertEqual(result, ["processed-off-loop"])

    async def test_first_poll_initializes_to_highest_uid_without_processing_history(self) -> None:
        client = _FakeClient(ImapMailboxFetchResult(uid_validity=77, highest_uid=42, emails=()))
        processor = _LoopDetectingProcessor()
        store = _RecordingSyncStore()
        poller = InboundMailPoller(client=client, processor=processor, interval_seconds=60,
                                    mailbox_monitor_id="mailbox-1", uid_validity=None,
                                    last_processed_uid=None, sync_store=store)
        result = await poller.poll_once()
        self.assertEqual(result, [])
        self.assertEqual(store.initialized, [("mailbox-1", 77, 42)])
        self.assertFalse(hasattr(processor, "emails"))
        self.assertEqual(poller.uid_validity, 77)
        self.assertEqual(poller.last_processed_uid, 42)

    async def test_failed_message_is_not_checkpointed_and_is_retried(self) -> None:
        message = InboundEmail("1", "<1@example.com>", "a@example.com", "sales@example.com", "A", "A", "A", "2026-08-05T00:00:00+00:00")
        client = _FakeClient(ImapMailboxFetchResult(uid_validity=1, highest_uid=1, emails=(message,)))
        poller = InboundMailPoller(client=client, processor=_FailingProcessor(), interval_seconds=60,
                                    mailbox_monitor_id="mailbox-1", uid_validity=1,
                                    last_processed_uid=0, sync_store=_RecordingSyncStore())

        with self.assertRaises(RuntimeError):
            await poller.poll_once()

        self.assertEqual(poller.last_processed_uid, 0)
        self.assertEqual(client.calls[-1][0], 0)

    async def test_poll_processes_new_uids_in_order_and_persists_each_checkpoint(self) -> None:
        messages = (
            InboundEmail("43", "<43@example.com>", "a@example.com", "sales@example.com", "A", "A", "A", "2026-08-05T00:00:00+00:00"),
            InboundEmail("44", "<44@example.com>", "b@example.com", "sales@example.com", "B", "B", "B", "2026-08-05T00:01:00+00:00"),
        )
        client = _FakeClient(ImapMailboxFetchResult(uid_validity=77, highest_uid=44, emails=messages))
        processor = _LoopDetectingProcessor()
        store = _RecordingSyncStore()
        poller = InboundMailPoller(client=client, processor=processor, interval_seconds=60,
                                    mailbox_monitor_id="mailbox-1", uid_validity=77,
                                    last_processed_uid=42, sync_store=store)
        result = await poller.poll_once()
        self.assertEqual(result, ["processed-off-loop", "processed-off-loop"])
        self.assertEqual(store.advanced, [("mailbox-1", 77, 43), ("mailbox-1", 77, 44)])
        self.assertEqual(store.successes, ["mailbox-1"])
        self.assertEqual(poller.last_processed_uid, 44)

    async def test_uid_validity_change_rebaselines_without_processing_messages(self) -> None:
        message = InboundEmail("99", "<99@example.com>", "a@example.com", "sales@example.com", "A", "A", "A", "2026-08-05T00:00:00+00:00")
        client = _FakeClient(ImapMailboxFetchResult(uid_validity=88, highest_uid=99, emails=(message,)))
        processor = _LoopDetectingProcessor()
        store = _RecordingSyncStore()
        poller = InboundMailPoller(client=client, processor=processor, interval_seconds=60,
                                    mailbox_monitor_id="mailbox-1", uid_validity=77,
                                    last_processed_uid=42, sync_store=store)
        result = await poller.poll_once()
        self.assertEqual(result, [])
        self.assertEqual(store.initialized, [("mailbox-1", 88, 99)])
        self.assertFalse(hasattr(processor, "emails"))

    def test_imap_first_sync_reads_highest_uid_without_fetching_history(self) -> None:
        session = _FakeMailboxSession(uid_validity=77, all_uids=b"40 41 42")
        client = ImapInboundMailClient(
            host="imap.example.com", port=993, username="sales@example.com", password="secret"
        )
        with patch("ltc.modules.customer_operation.application.inbound_mail_service.imaplib.IMAP4_SSL", return_value=session):
            result = client.fetch_since(last_processed_uid=None, expected_uid_validity=None)

        self.assertEqual(result.uid_validity, 77)
        self.assertEqual(result.highest_uid, 42)
        self.assertEqual(result.emails, ())
        self.assertEqual(session.select_args, ("INBOX", True))
        self.assertFalse(any(call[0] == "fetch" for call in session.uid_calls))

    def test_imap_history_fetch_reads_existing_messages_for_backfill(self) -> None:
        session = _FakeMailboxSession(uid_validity=77, all_uids=b"41 42 43")
        client = ImapInboundMailClient(host="imap.example.com", port=993, username="sales@example.com", password="secret")
        with patch("ltc.modules.customer_operation.application.inbound_mail_service.imaplib.IMAP4_SSL", return_value=session):
            result = client.fetch_history()
        self.assertEqual([email.uid for email in result.emails], ["41", "42", "43"])
        self.assertEqual([call[1] for call in session.uid_calls if call[0] == "fetch"], ["41", "42", "43"])

    def test_imap_fetches_only_uids_after_persisted_checkpoint(self) -> None:
        session = _FakeMailboxSession(uid_validity=77, all_uids=b"40 41 42 43 44", new_uids=b"43 44")
        client = ImapInboundMailClient(
            host="imap.example.com", port=993, username="sales@example.com", password="secret"
        )
        with patch("ltc.modules.customer_operation.application.inbound_mail_service.imaplib.IMAP4_SSL", return_value=session):
            result = client.fetch_since(last_processed_uid=42, expected_uid_validity=77)

        self.assertEqual([message.uid for message in result.emails], ["43", "44"])
        self.assertIn(("search", None, "UID 43:*"), session.uid_calls)
        self.assertEqual([call[1] for call in session.uid_calls if call[0] == "fetch"], ["43", "44"])

    def test_html_only_email_preview_is_plain_text(self) -> None:
        raw = b"\r\n".join(
            [
                b"From: sender@example.com",
                b"To: sales@example.com",
                b"Subject: HTML notice",
                b"Content-Type: text/html; charset=utf-8",
                b"",
                b"<html><head><style>.secret{display:none}</style></head><body><p>Hello &amp; welcome</p><div>Next step</div></body></html>",
            ]
        )

        parsed = parse_raw_email("1", raw)

        self.assertIn("Hello & welcome", parsed.body_text)
        self.assertIn("Next step", parsed.body_preview)
        self.assertNotIn("<style>", parsed.body_text)
        self.assertNotIn("display:none", parsed.body_preview)


    def test_multipart_email_collects_attachments(self) -> None:
        raw = b"\r\n".join(
            [
                b"From: sender@example.com",
                b"To: sales@example.com",
                b"Subject: Proposal",
                b"MIME-Version: 1.0",
                b"Content-Type: multipart/mixed; boundary=boundary",
                b"",
                b"--boundary",
                b"Content-Type: text/plain; charset=utf-8",
                b"",
                b"Please review the attached proposal.",
                b"--boundary",
                b"Content-Type: text/plain; name=proposal.txt",
                b"Content-Disposition: attachment; filename=proposal.txt",
                b"",
                "方案一：年度方案".encode("utf-8"),
                b"--boundary--",
            ]
        )

        parsed = parse_raw_email("2", raw)

        self.assertEqual(len(parsed.attachments), 1)
        self.assertEqual(parsed.attachments[0].filename, "proposal.txt")
        self.assertIn("方案一", parsed.attachments[0].content.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
