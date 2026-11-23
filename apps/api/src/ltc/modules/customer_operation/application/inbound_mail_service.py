import asyncio
import email
import imaplib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parseaddr
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable

from ltc.modules.customer_operation.infrastructure.mail_store import PostgresMailStore
from ltc.modules.customer_operation.application.email_attachment_models import EmailAttachmentInput
from ltc.modules.customer_operation.application.pa_notification_service import PaNotificationService
from ltc.modules.customer_operation.application.analysis_trigger import (
    trigger_customer_analysis_best_effort,
)


PROCESSED_FILE = "inbound-mail-processed.json"
INBOUND_HISTORY_FILE = "inbound-mail-history.json"


@dataclass(frozen=True)
class InboundEmail:
    uid: str
    message_id: str
    from_email: str
    to_email: str
    subject: str
    body_preview: str
    body_text: str
    received_at: str
    in_reply_to: str = ""
    attachments: tuple[EmailAttachmentInput, ...] = ()


@dataclass(frozen=True)
class ImapMailboxFetchResult:
    uid_validity: int
    highest_uid: int
    emails: tuple[InboundEmail, ...]


class _HtmlTextParser(HTMLParser):
    """Extract readable text from HTML-only messages without rendering markup."""

    _ignored_tags = {"head", "script", "style", "title"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self._ignored_tags:
            self._ignored_depth += 1
        elif tag in {"br", "div", "p", "li", "tr"} and self._ignored_depth == 0:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._ignored_tags and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0:
            self.parts.append(data)


def _html_to_text(value: str) -> str:
    parser = _HtmlTextParser()
    try:
        parser.feed(value)
        parser.close()
        return unescape("".join(parser.parts))
    except Exception:
        return re.sub(r"<[^>]+>", " ", unescape(value))


def _decode_mime_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value))).strip()
    except Exception:
        return str(value or "").strip()


def _extract_email_address(value: str | None) -> str:
    decoded = _decode_mime_header(value)
    _, address = parseaddr(decoded)
    return (address or decoded).strip().lower()


def _extract_body(message: Message) -> str:
    if message.is_multipart():
        plain_parts = []
        fallback_parts = []
        for part in message.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition") or "").lower()
            if "attachment" in disposition:
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if content_type == "text/plain":
                plain_parts.append(text)
            elif content_type == "text/html":
                fallback_parts.append(_html_to_text(text))
        plain_text = "\n".join(plain_parts)
        html_text = "\n".join(fallback_parts)
        html_lower = html_text.casefold()
        if any(token in html_lower for token in ("delivery failed", "delivery status notification", "unable to send to", "final-recipient", "\u65e0\u6cd5\u53d1\u9001\u5230", "\u9000\u4fe1\u539f\u56e0", "\u88ab\u9000\u56de\u90ae\u4ef6")):
            return "\n".join(part for part in (plain_text, html_text) if part)
        return plain_text or html_text

    payload = message.get_payload(decode=True)
    if not payload:
        return ""
    text = payload.decode(message.get_content_charset() or "utf-8", errors="replace")
    return _html_to_text(text) if message.get_content_type() == "text/html" else text



def _extract_attachments(message: Message) -> tuple[EmailAttachmentInput, ...]:
    attachments: list[EmailAttachmentInput] = []
    if not message.is_multipart():
        return ()
    for part in message.walk():
        disposition = str(part.get("Content-Disposition") or "").lower()
        filename = _decode_mime_header(part.get_filename())
        if "attachment" not in disposition and not filename:
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        attachments.append(
            EmailAttachmentInput(
                filename=filename or "attachment.bin",
                content_type=part.get_content_type() or "application/octet-stream",
                content=payload,
            )
        )
    return tuple(attachments)

def _preview(text: str, limit: int = 180) -> str:
    compact = " ".join(str(text or "").split())
    return compact[:limit]


def parse_raw_email(uid: str, raw: bytes) -> InboundEmail:
    message = email.message_from_bytes(raw)
    message_id = str(message.get("Message-ID") or "").strip() or f"imap-uid:{uid}"
    received_at = str(message.get("Date") or "").strip() or datetime.now(timezone.utc).isoformat()
    body_text = _extract_body(message)
    return InboundEmail(
        uid=str(uid),
        message_id=message_id,
        from_email=_extract_email_address(message.get("From")),
        to_email=_extract_email_address(message.get("To")),
        subject=_decode_mime_header(message.get("Subject")),
        body_preview=_preview(body_text),
        body_text=body_text,
        received_at=received_at,
        in_reply_to=_decode_mime_header(message.get("In-Reply-To")),
        attachments=_extract_attachments(message),
    )


def normalize_inbound_email(email_item: InboundEmail) -> dict[str, Any]:
    body = email_item.body_preview or email_item.subject or email_item.from_email
    return {
        "eventType": "imap.received",
        "messageId": email_item.message_id or f"imap-uid:{email_item.uid}",
        "companyId": "",
        "emailId": "",
        "customerName": "",
        "from": email_item.from_email,
        "to": email_item.to_email,
        "subject": email_item.subject,
        "bodyPreview": email_item.body_preview,
        "bodyText": email_item.body_text,
        "inReplyTo": email_item.in_reply_to,
        "priority": "high",
        "notificationTitle": "閺€璺哄煂 163 闁喚顔堥弶銉や繆",
        "notificationBody": body,
        "createdAt": email_item.received_at,
        "raw": {
            "uid": email_item.uid,
            "message_id": email_item.message_id,
            "from": email_item.from_email,
            "to": email_item.to_email,
            "subject": email_item.subject,
            "body_preview": email_item.body_preview,
            "body_text": email_item.body_text,
            "received_at": email_item.received_at,
            "in_reply_to": email_item.in_reply_to,
        },
    }


class InboundMailProcessor:
    def __init__(
        self,
        *,
        data_dir: Path | None = None,
        notification_service: PaNotificationService | None = None,
        sales_user_id: str = "",
    ) -> None:
        self.data_dir = data_dir
        self.notification_service = notification_service or PaNotificationService(data_dir=data_dir)
        self.sales_user_id = sales_user_id

    def _path(self, filename: str) -> Path:
        if self.data_dir is not None:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            return self.data_dir / filename
        from ltc.modules.customer_operation.infrastructure.legacy_file_store import LegacyFileStore

        return LegacyFileStore().data_dir / filename

    def _read_json_array(self, filename: str) -> list[dict[str, Any]]:
        path = self._path(filename)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig") or "[]")
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []

    def _write_json_array(self, filename: str, items: list[dict[str, Any]]) -> None:
        path = self._path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    def process_emails(self, emails: Iterable[InboundEmail]) -> list[dict[str, Any]]:
        postgres_store = PostgresMailStore()
        history = self._read_json_array(INBOUND_HISTORY_FILE)
        created = []

        for email_item in emails:
            event = normalize_inbound_email(email_item)
            event["salesUserId"] = self.sales_user_id
            if postgres_store.is_configured():
                delivery_update = postgres_store.reconcile_delivery_notification(
                    from_email=email_item.from_email,
                    subject=email_item.subject,
                    body_text=email_item.body_text,
                    in_reply_to=email_item.in_reply_to or None,
                    attachments=list(email_item.attachments),
                )
                if delivery_update:
                    event["deliveryUpdate"] = delivery_update
                stored = postgres_store.record_inbound_email(
                    from_email=email_item.from_email,
                    to_email=email_item.to_email,
                    subject=email_item.subject,
                    body_text=email_item.body_text,
                    body_preview=email_item.body_preview,
                    message_id_header=email_item.message_id,
                    in_reply_to=email_item.in_reply_to or None,
                    received_at=email_item.received_at,
                    sales_user_id=self.sales_user_id,
                    attachments=list(email_item.attachments),
                    related_email_id=(delivery_update or {}).get("emailId") if delivery_update else None,
                )
                if stored is None or not stored.created:
                    continue
                event["companyId"] = str(stored.company_id or "")
                event["emailId"] = str(stored.email_id or "")
                if stored.company_id:
                    trigger_customer_analysis_best_effort(
                        stored.company_id,
                        source="inbound_email",
                    )
            notification = self.notification_service.get_notification(
                str(event.get("emailId") or ""), user_id=self.sales_user_id
            )
            if notification is not None:
                created.append(notification)
            history.insert(0, event)

        if created:
            self._write_json_array(INBOUND_HISTORY_FILE, history[:500])
        return created



def get_inbound_email_detail_for_notification(
    notification_id: str,
    *,
    data_dir: Path | None = None,
    notification_service: PaNotificationService | None = None,
    user_id: str = "",
) -> dict[str, Any]:
    service = notification_service or PaNotificationService()
    detail = service.get_detail(notification_id, user_id=user_id)
    if detail is None:
        raise KeyError(notification_id)
    return detail


class ImapInboundMailClient:
    def __init__(self, *, host: str, port: int, username: str, password: str, mailbox: str = "INBOX") -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.mailbox = mailbox

    def fetch_since(
        self,
        *,
        last_processed_uid: int | None,
        expected_uid_validity: int | None,
        limit: int = 20,
    ) -> ImapMailboxFetchResult:
        with imaplib.IMAP4_SSL(self.host, self.port) as client:
            self._login(client)
            self._send_client_id(client)
            select_status, select_data = client.select(self.mailbox, readonly=True)
            if select_status != "OK":
                raise RuntimeError(f"Unable to select mailbox {self.mailbox}: {select_status} {select_data}")

            uid_validity = self._uid_validity(client)
            status, data = client.uid("search", None, "ALL")
            if status != "OK":
                raise RuntimeError(f"Unable to list mailbox UIDs: {status} {data}")
            all_uids = self._parse_uid_list(data)
            highest_uid = all_uids[-1] if all_uids else 0

            if last_processed_uid is None or expected_uid_validity != uid_validity:
                return ImapMailboxFetchResult(
                    uid_validity=uid_validity,
                    highest_uid=highest_uid,
                    emails=(),
                )
            if highest_uid <= last_processed_uid:
                return ImapMailboxFetchResult(
                    uid_validity=uid_validity,
                    highest_uid=highest_uid,
                    emails=(),
                )

            status, data = client.uid(
                "search",
                None,
                f"UID {last_processed_uid + 1}:*",
            )
            if status != "OK":
                raise RuntimeError(f"Unable to search new mailbox UIDs: {status} {data}")
            uids = [uid for uid in self._parse_uid_list(data) if uid > last_processed_uid][:limit]
            emails = []
            for uid_value in uids:
                uid = str(uid_value)
                fetch_status, fetched = client.uid("fetch", uid, "(BODY.PEEK[])")
                if fetch_status != "OK":
                    raise RuntimeError(f"Unable to fetch mailbox UID {uid}: {fetch_status} {fetched}")
                raw = next(
                    (item[1] for item in fetched if isinstance(item, tuple) and isinstance(item[1], bytes)),
                    None,
                )
                if raw is None:
                    raise RuntimeError(f"Mailbox UID {uid} returned no message body")
                emails.append(parse_raw_email(uid, raw))
            return ImapMailboxFetchResult(
                uid_validity=uid_validity,
                highest_uid=highest_uid,
                emails=tuple(emails),
            )

    def fetch_history(self, *, limit: int | None = None) -> ImapMailboxFetchResult:
        with imaplib.IMAP4_SSL(self.host, self.port) as client:
            self._login(client)
            self._send_client_id(client)
            select_status, select_data = client.select(self.mailbox, readonly=True)
            if select_status != "OK":
                raise RuntimeError(f"Unable to select mailbox {self.mailbox}: {select_status} {select_data}")
            uid_validity = self._uid_validity(client)
            status, data = client.uid("search", None, "ALL")
            if status != "OK":
                raise RuntimeError(f"Unable to list mailbox UIDs: {status} {data}")
            all_uids = self._parse_uid_list(data)
            selected_uids = all_uids[-max(1, limit):] if limit is not None else all_uids
            emails = []
            for uid_value in selected_uids:
                uid = str(uid_value)
                fetch_status, fetched = client.uid("fetch", uid, "(BODY.PEEK[])")
                if fetch_status != "OK":
                    raise RuntimeError(f"Unable to fetch mailbox UID {uid}: {fetch_status} {fetched}")
                raw = next((item[1] for item in fetched if isinstance(item, tuple) and isinstance(item[1], bytes)), None)
                if raw is None:
                    raise RuntimeError(f"Mailbox UID {uid} returned no message body")
                emails.append(parse_raw_email(uid, raw))
            return ImapMailboxFetchResult(
                uid_validity=uid_validity,
                highest_uid=all_uids[-1] if all_uids else 0,
                emails=tuple(emails),
            )

    @staticmethod
    def _parse_uid_list(data: Any) -> list[int]:
        if not data:
            return []
        raw = data[0] or b""
        if isinstance(raw, str):
            raw = raw.encode("ascii", errors="ignore")
        return sorted(int(value) for value in raw.split() if value.isdigit())

    @staticmethod
    def _uid_validity(client: Any) -> int:
        _, values = client.response("UIDVALIDITY")
        if not values:
            raise RuntimeError("IMAP server did not provide UIDVALIDITY")
        raw = values[-1]
        if isinstance(raw, bytes):
            raw = raw.decode("ascii", errors="ignore")
        match = re.search(r"\d+", str(raw or ""))
        if match is None:
            raise RuntimeError("IMAP server returned an invalid UIDVALIDITY")
        return int(match.group(0))

    def _login(self, client: Any) -> None:
        try:
            self.username.encode("ascii")
            self.password.encode("ascii")
        except UnicodeEncodeError:
            credentials = f"\0{self.username}\0{self.password}".encode("utf-8")
            client.authenticate("PLAIN", lambda _challenge: credentials)
            return
        client.login(self.username, self.password)

    def _send_client_id(self, client: Any) -> None:
        payload = '("name" "LTC Customer Operation Agent" "version" "1.0" "vendor" "LTC")'
        try:
            imaplib.Commands.setdefault("ID", ("AUTH", "SELECTED"))
            client._simple_command("ID", payload)
        except Exception as exc:
            print(f"[inbound-mail] IMAP ID command skipped: {exc}")


class InboundMailPoller:
    def __init__(
        self,
        *,
        client: ImapInboundMailClient,
        processor: InboundMailProcessor,
        interval_seconds: int,
        mailbox_monitor_id: str,
        uid_validity: int | None,
        last_processed_uid: int | None,
        sync_store: Any,
    ) -> None:
        self.client = client
        self.processor = processor
        self.interval_seconds = max(10, int(interval_seconds or 60))
        self.mailbox_monitor_id = mailbox_monitor_id
        self.uid_validity = uid_validity
        self.last_processed_uid = last_processed_uid
        self.sync_store = sync_store
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stopped.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopped.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def poll_once(self) -> list[dict[str, Any]]:
        try:
            fetched = await asyncio.to_thread(
                self.client.fetch_since,
                last_processed_uid=self.last_processed_uid,
                expected_uid_validity=self.uid_validity,
            )
            if self.last_processed_uid is None or self.uid_validity != fetched.uid_validity:
                await asyncio.to_thread(
                    self.sync_store.initialize,
                    self.mailbox_monitor_id,
                    fetched.uid_validity,
                    fetched.highest_uid,
                )
                self.uid_validity = fetched.uid_validity
                self.last_processed_uid = fetched.highest_uid
                return []

            notifications: list[dict[str, Any]] = []
            for email_item in fetched.emails:
                # Parsing, database writes and the optional synchronous LLM bridge all
                # block. Keep the API event loop free and checkpoint only after the
                # message reached a terminal processed or intentionally skipped state.
                try:
                    notifications.extend(
                        await asyncio.to_thread(self.processor.process_emails, [email_item])
                    )
                except Exception as exc:
                    try:
                        await asyncio.to_thread(
                            self.sync_store.record_error,
                            self.mailbox_monitor_id,
                            f"UID {email_item.uid}: {exc}",
                        )
                    except Exception:
                        pass
                    raise
                processed_uid = int(email_item.uid)
                await asyncio.to_thread(
                    self.sync_store.advance,
                    self.mailbox_monitor_id,
                    fetched.uid_validity,
                    processed_uid,
                )
                self.last_processed_uid = processed_uid
            await asyncio.to_thread(self.sync_store.record_success, self.mailbox_monitor_id)
            return notifications
        except Exception as exc:
            try:
                await asyncio.to_thread(
                    self.sync_store.record_error,
                    self.mailbox_monitor_id,
                    str(exc),
                )
            except Exception:
                pass
            raise

    async def _run(self) -> None:
        while not self._stopped.is_set():
            try:
                await self.poll_once()
            except Exception as exc:
                print(f"[inbound-mail] poll failed: {exc}")
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                continue
