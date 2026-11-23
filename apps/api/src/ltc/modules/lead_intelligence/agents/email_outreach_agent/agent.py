from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol
from uuid import uuid4


LOGGER = logging.getLogger(__name__)
AGENT_NAME = "email-outreach-agent"
CHANNEL_TEXT_MARKERS = (
    "travel agency",
    "tmc",
    "corporate travel",
    "tour operator",
    "group travel",
    "airline",
    "hotel",
    "cruise",
    "ota",
    "travel platform",
    "\u65c5\u884c\u793e",
    "\u65c5\u6e38\u5e73\u53f0",
    "\u65c5\u884c\u5e73\u53f0",
    "\u5546\u65c5\u5e73\u53f0",
    "\u65c5\u6e38\u8fd0\u8425\u5546",
    "\u822a\u7a7a\u516c\u53f8",
    "\u9152\u5e97",
    "\u90ae\u8f6e",
)
CHANNEL_INDUSTRY_MARKERS = (
    "tmc",
    "travel_agency",
    "travel agency",
    "tour_operator",
    "tour operator",
    "travel_ota",
    "ota",
    "airline",
    "hotel",
    "cruise",
)
ENTERPRISE_MARKERS = (
    "enterprise",
    "multi-country",
    "multi country",
    "global offices",
    "remote team",
    "cross-border operations",
    "cross-border workforce",
    "global workforce",
    "international business travel",
    "frequent international travel",
    "\u51fa\u6d77",
    "\u8de8\u5883\u529e\u516c",
    "\u8de8\u5883\u56e2\u961f",
    "\u5168\u7403\u529e\u516c\u5ba4",
    "\u8fdc\u7a0b\u56e2\u961f",
    "\u56fd\u9645\u5546\u52a1\u65c5\u884c",
    "\u56fd\u9645\u5dee\u65c5",
    "\u591a\u56fd\u529e\u516c",
)

ENTERPRISE_TEMPLATE_SUBJECTS = (
    "Cross-border connectivity & enterprise eSIM for {company}",
    "Global connectivity, one plan \u2014 for {company}",
)
ENTERPRISE_TEMPLATE_SUBJECT = ENTERPRISE_TEMPLATE_SUBJECTS[0]
ENTERPRISE_TEMPLATE_BODY = """Hi {contact},

We understand that {company} places great importance on efficient, reliable, and cost-effective business travel management. As international business travel continues to recover and expand, mobile connectivity has become an essential part of employee productivity, travel safety, and overall travel experience.

With this in mind, we would like to explore potential collaboration opportunities with {company} around our enterprise eSIM travel platform.

Our solution is designed specifically for companies with frequent international travel needs, helping businesses provide employees with fast and flexible connectivity across global destinations without relying on physical SIM cards, expensive roaming plans, or manual procurement processes.

Through our enterprise eSIM platform, {company} can benefit from:

Global eSIM coverage across major business travel destinations;

Centralized purchase, distribution, and management of eSIM plans for employees;

Lower and more transparent connectivity costs compared with traditional roaming;

Fast activation before or upon arrival, improving employee travel efficiency;

Flexible data packages based on destination, duration, and business needs;

Usage visibility and management tools to support cost control;

Scalable support for individual business travelers, project teams, and group travel;

Optional branded or customized solutions for corporate travel programs.

For employees, eSIMs provide a smoother travel experience by allowing them to stay connected immediately upon arrival, without searching for local SIM cards or dealing with complicated roaming activation. For the company, our platform helps simplify travel connectivity management, reduce communication costs, and improve operational efficiency.

At this stage, we would first like to learn more about {company}'s business travel volume, key destinations, employee connectivity needs, and current mobile data management process. Based on those requirements, we can discuss a suitable enterprise eSIM solution and partnership model.

Would you be available for a 20-minute online meeting in the near future? We would welcome the opportunity to briefly introduce our platform capabilities, global coverage, pricing advantages, and enterprise management features.

We look forward to your reply. Thank you!

Best regards,
{sales}"""

PARTNER_TEMPLATE_SUBJECTS = (
    "Exploring eSIM partnership with {company}",
    "eSIM as a value-add for {company}'s travelers",
    "Connectivity as part of the travel experience \u2014 {company}",
)
PARTNER_TEMPLATE_SUBJECT = PARTNER_TEMPLATE_SUBJECTS[0]
PARTNER_TEMPLATE_BODY = """Hi {contact},

We understand that {company} has long been committed to providing professional,
personalized travel services across leisure travel, business travel, and group
travel. As international travelers increasingly expect to be connected as soon
as they arrive, connectivity has become an essential part of the overall travel
experience.

With this in mind, we would like to explore potential collaboration
opportunities with {company} around eSIM products and services.

For leisure travelers, eSIMs enable fast connectivity upon arrival, reducing the
need to purchase physical SIM cards or activate international roaming. For
business and group travelers, eSIMs can also improve travel efficiency, optimize
connectivity costs, and offer more flexible options for travel management.

We believe eSIM services could complement {company}'s existing travel products
and customer service in several ways, including:
- As a value-added service alongside flights, hotels, or travel packages;
- Providing convenient and flexible connectivity solutions for international
  business travelers;
- Supporting centralized eSIM procurement and management for group and
  corporate clients;
- Exploring co-marketing, resale, or referral partnership models; and
- Further enhancing the customer travel experience through options such as
  branded customization.

At this stage, we would first like to learn more about {company}'s customer
profile, priority markets, and business needs, and then discuss a suitable
partnership approach based on those requirements. During a call, we can also
briefly introduce our coverage, service capabilities, and partnership models.

Would you be available for a 20-minute online meeting in the near future? We
would welcome the opportunity to hear your thoughts and explore how eSIM
services can best integrate into {company}'s travel solutions.

We look forward to your reply. Thank you!

Best regards,
{sales}"""

COUNTRY_LANGUAGE_MAP = {
    "CN": "zh",
    "TW": "zh",
    "HK": "zh",
    "JP": "ja",
    "KR": "en",
    "FR": "fr",
    "DE": "de",
    "AT": "de",
    "CH": "de",
    "ES": "es",
    "MX": "es",
}


def target_language_for_candidate(candidate: dict[str, Any]) -> str:
    country_code = str(candidate.get("country_code") or "").strip().upper()
    if country_code in COUNTRY_LANGUAGE_MAP:
        return COUNTRY_LANGUAGE_MAP[country_code]
    return "en"



def template_blueprint_for_candidate(candidate: dict[str, Any]) -> str:
    template = choose_template(candidate)
    return {
        "partner": PARTNER_TEMPLATE_BODY,
        "enterprise": ENTERPRISE_TEMPLATE_BODY,
    }[template]


@dataclass(frozen=True)
class AutoTouchConfig:
    enabled: bool = False
    interval_minutes: int = 60
    min_score: float = 75
    regions: tuple[str, ...] = ("NA", "EU")
    max_per_run: int = 0
    selected_contact_ids: tuple[str, ...] = ()
    sender_user_id: str = ""
    sales_name: str = "Global Marketing Team"
    template_subject: str = ""
    template_body: str = ""


class OutreachStore(Protocol):
    def start_run(self, config: AutoTouchConfig) -> str: ...
    def find_candidates(self, config: AutoTouchConfig) -> list[dict[str, Any]]: ...
    def claim_candidate(self, *, run_id: str, company_id: str, contact_id: str) -> bool: ...
    def find_existing_delivery(self, *, company_id: str, contact_id: str) -> str | None: ...
    def mark_success(self, *, run_id: str, company_id: str, contact_id: str, message_id: str) -> None: ...
    def mark_failure(self, *, run_id: str, company_id: str, contact_id: str, error: str) -> None: ...
    def finish_run(self, *, run_id: str, summary: dict[str, Any]) -> None: ...
    def fail_run(self, *, run_id: str, error: str) -> None: ...


EmailAgentRunner = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
EmailSender = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def choose_template_details(candidate: dict[str, Any]) -> tuple[str, str]:
    industry_code = str(candidate.get("industry_code") or "").strip().lower()
    intro = str(candidate.get("company_intro") or "").strip().lower()
    company_name = str(candidate.get("company_name") or "").strip().lower()
    text = " ".join((industry_code, intro, company_name))

    if any(marker in industry_code for marker in CHANNEL_INDUSTRY_MARKERS):
        return "partner", "travel_channel_industry"
    if any(marker in text for marker in CHANNEL_TEXT_MARKERS):
        return "partner", "travel_channel_markers"
    if any(marker in text for marker in ENTERPRISE_MARKERS):
        return "enterprise", "enterprise_direct_markers"
    return "enterprise", "default_enterprise"


def choose_template(candidate: dict[str, Any]) -> str:
    return choose_template_details(candidate)[0]


def _subject_for_template(template: str, candidate: dict[str, Any]) -> str:
    subjects = PARTNER_TEMPLATE_SUBJECTS if template == "partner" else ENTERPRISE_TEMPLATE_SUBJECTS
    seed = "|".join(
        str(candidate.get(field) or "").strip().lower()
        for field in ("company_id", "contact_id", "company_name", "contact_name")
    )
    index = int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16) % len(subjects)
    return subjects[index]


def _fallback_email(candidate: dict[str, Any], config: AutoTouchConfig) -> tuple[str, str]:
    company = str(candidate.get("company_name") or "your company").strip()
    contact = str(candidate.get("contact_name") or "there").strip()
    template = config.template_body.strip()
    language = target_language_for_candidate(candidate)
    if template:
        body = template.replace("{company}", company).replace("{contact}", contact).replace("{sales}", config.sales_name)
        subject = config.template_subject.strip() or PARTNER_TEMPLATE_SUBJECT
        return subject.replace("{company}", company), body
    if language == "en":
        template = choose_template(candidate)
        templates = {
            "partner": PARTNER_TEMPLATE_BODY,
            "enterprise": ENTERPRISE_TEMPLATE_BODY,
        }
        body_template = templates[template]
        subject_template = _subject_for_template(template, candidate)
        return (
            subject_template.replace("{company}", company),
            body_template.replace("{company}", company).replace("{contact}", contact).replace("{sales}", config.sales_name),
        )

    fallbacks = {
        "fr": (
            f"Découvrir la connectivité eSIM pour {company}",
            f"""Bonjour {contact},

Nous souhaitons comprendre les besoins de {company} en matière de connectivité internationale et voir si une solution eSIM multi-pays pourrait vous aider.

Seriez-vous disponible pour un échange de 20 minutes ?

Cordialement,
{config.sales_name}""",
        ),
        "de": (
            f"Internationale eSIM-Konnektivität für {company}",
            f"""Hallo {contact},

wir möchten die Anforderungen von {company} an internationale Konnektivität besser verstehen und prüfen, ob eine länderübergreifende eSIM-Lösung hilfreich sein könnte.

Wären Sie für ein 20-minütiges Gespräch verfügbar?

Viele Grüße,
{config.sales_name}""",
        ),
        "es": (
            f"Conectividad eSIM internacional para {company}",
            f"""Hola {contact},

Nos gustaría conocer las necesidades de conectividad internacional de {company} y evaluar si una solución eSIM para varios países podría ser útil.

¿Estaría disponible para una reunión de 20 minutos?

Saludos cordiales,
{config.sales_name}""",
        ),
        "ja": (
            f"{company}向け国際eSIM接続について",
            f"""{contact}様

{company}の国際接続ニーズを理解し、複数国対応のeSIMソリューションをご提案したいと考えています。

20分ほどお話しする機会をいただけますでしょうか。

よろしくお願いいたします。
{config.sales_name}""",
        ),
        "zh": (
            f"探索 {company} 的国际 eSIM 连接方案",
            f"""您好，{contact}：

我们希望了解 {company} 的国际连接需求，并探讨多国 eSIM 方案是否能够提供帮助。

您近期是否方便进行一次 20 分钟的线上沟通？

此致
{config.sales_name}""",
        ),
    }
    subject, body = fallbacks.get(
        language,
        (
            f"Exploring cross-border eSIM connectivity with {company}",
            f"""Hi {contact},

We would like to understand {company}'s international connectivity needs and explore whether a multi-country eSIM solution could help.

Would you be available for a 20-minute online meeting?

Best regards,
{config.sales_name}""",
        ),
    )
    return subject, body



def _source_template_email(candidate: dict[str, Any], config: AutoTouchConfig) -> tuple[str, str]:
    source_candidate = dict(candidate)
    source_candidate["country_code"] = "US"
    prd_config = AutoTouchConfig(sales_name=config.sales_name)
    return _fallback_email(source_candidate, prd_config)


def build_translation_segments(source_body: str) -> list[dict[str, str]]:
    segments: list[dict[str, str]] = []
    paragraph_index = 0
    bullet_index = 0
    for block in re.split(r"\n\s*\n", source_body.strip()):
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        normal_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("- "):
                if normal_lines:
                    paragraph_index += 1
                    segments.append({"id": f"P{paragraph_index}", "kind": "paragraph", "text": "\n".join(normal_lines)})
                    normal_lines = []
                bullet_index += 1
                segments.append({"id": f"B{bullet_index}", "kind": "bullet", "text": stripped[2:].strip()})
            elif line[:1].isspace() and segments and segments[-1]["kind"] == "bullet":
                segments[-1]["text"] += " " + stripped
            else:
                normal_lines.append(stripped)
        if normal_lines:
            paragraph_index += 1
            segments.append({"id": f"P{paragraph_index}", "kind": "paragraph", "text": "\n".join(normal_lines)})
    return segments


def reassemble_translation_segments(
    source_segments: list[dict[str, str]], translated_segments: dict[str, str],
) -> str:
    source_ids = {segment["id"] for segment in source_segments}
    missing = [segment_id for segment_id in source_ids if not str(translated_segments.get(segment_id) or "").strip()]
    extra = sorted(set(translated_segments) - source_ids)
    if missing:
        raise RuntimeError(f"Structured translation missing translation segment(s): {', '.join(missing)}")
    if extra:
        raise RuntimeError(f"Structured translation returned unexpected segment(s): {', '.join(extra)}")
    output: list[str] = []
    previous_kind = ""
    for segment in source_segments:
        segment_id = segment["id"]
        kind = segment["kind"]
        text = str(translated_segments[segment_id]).strip()
        if kind == "bullet":
            output.append(f"- {text}")
        else:
            if output and previous_kind != "bullet":
                output.append("")
            elif output and previous_kind == "bullet":
                output.append("")
            output.append(text)
        previous_kind = kind
    return "\n".join(output).strip()


def append_sales_signature(body: str, sales_name: str) -> str:
    clean_body = body.strip()
    clean_sales_name = sales_name.strip()
    if not clean_sales_name or clean_sales_name.lower() in clean_body.lower():
        return clean_body
    signoff = f"Best regards,\n{clean_sales_name}"
    return f"{clean_body}\n\n{signoff}" if clean_body else signoff


def _validate_complete_translation(
    *,
    source_subject: str,
    source_body: str,
    translated_subject: str,
    translated_body: str,
    candidate: dict[str, Any],
    sales_name: str,
) -> None:
    source_paragraphs = [part.strip() for part in re.split(r"\n\s*\n", source_body) if part.strip()]
    translated_paragraphs = [part.strip() for part in re.split(r"\n\s*\n", translated_body) if part.strip()]
    if len(translated_paragraphs) != len(source_paragraphs):
        raise RuntimeError("Template translation did not preserve the PRD paragraph structure.")

    source_bullets = [line for line in source_body.splitlines() if line.startswith("- ")]
    translated_bullets = [line for line in translated_body.splitlines() if line.startswith("- ")]
    if len(translated_bullets) != len(source_bullets):
        raise RuntimeError("Template translation did not preserve all PRD bullet points.")

    company = str(candidate.get("company_name") or "").strip()
    contact = str(candidate.get("contact_name") or "").strip()
    for value, label in ((company, "company name"), (contact, "contact name"), (sales_name.strip(), "sales signature")):
        if value and value not in translated_body:
            raise RuntimeError(f"Template translation did not preserve the {label}.")
    if company and company not in translated_subject:
        raise RuntimeError("Template translation did not preserve the company name in the subject.")

    for number in set(re.findall(r"\d+(?:[.,]\d+)?", source_subject + "\n" + source_body)):
        if number not in translated_subject and number not in translated_body:
            raise RuntimeError(f"Template translation did not preserve required number {number}.")
    if "esim" in source_body.lower() and "esim" not in translated_body.lower():
        raise RuntimeError("Template translation did not preserve the eSIM product name.")



def _translation_correction_prompt(error: str) -> str:
    clean_error = str(error or "").strip()
    if not clean_error:
        return ""
    return (
        "\n\nPrevious translation failed quality validation:\n"
        f"- {clean_error}\n"
        "Correct this specific issue in the next response. Preserve every source segment ID, "
        "paragraph, bullet, required number, company name, contact name, product name, and sales signature. "
        "Return the complete structured translation, not a summary."
    )


class EmailAutomationAgent:
    def __init__(
        self,
        *,
        store: OutreachStore,
        email_agent: EmailAgentRunner,
        sender: EmailSender,
    ) -> None:
        self.store = store
        self.email_agent = email_agent
        self.sender = sender

    async def _process_candidate(
        self,
        *,
        candidate: dict[str, Any],
        config: AutoTouchConfig,
        run_id: str,
        semaphore: asyncio.Semaphore,
    ) -> dict[str, Any]:
        async with semaphore:
            company_id = str(candidate.get("company_id") or "")
            contact_id = str(candidate.get("contact_id") or "")
            if not company_id or not contact_id:
                return {"status": "skipped"}
            if not self.store.claim_candidate(run_id=run_id, company_id=company_id, contact_id=contact_id):
                return {"status": "skipped"}
            existing_message_id = self.store.find_existing_delivery(
                company_id=company_id,
                contact_id=contact_id,
            )
            if existing_message_id:
                self.store.mark_success(
                    run_id=run_id,
                    company_id=company_id,
                    contact_id=contact_id,
                    message_id=existing_message_id,
                )
                return {"companyId": company_id, "status": "sent", "messageId": existing_message_id, "attempts": 0}
            subject, body = _source_template_email(candidate, config)
            source_subject, source_body = subject, body
            source_segments = build_translation_segments(source_body)
            target_language = target_language_for_candidate(candidate)
            payload = {
                "operation": "translate" if target_language != "en" else "generate",
                "companyId": company_id,
                "contactId": contact_id,
                "customerName": candidate.get("company_name"),
                "recipientName": candidate.get("contact_name"),
                "recipientEmail": candidate.get("recipient_email"),
                "salesName": config.sales_name,
                "salesUserId": config.sender_user_id,
                "userId": config.sender_user_id,
                "audience": choose_template(candidate),
                "targetLanguage": target_language,
                "templateBlueprint": template_blueprint_for_candidate(candidate),
                "currentSubject": subject,
                "currentBody": body,
                "subject": subject,
                "body": body,
                "structuredTranslation": target_language != "en",
                "translationSegments": source_segments,
                "customPrompt": (
                    "Translate the complete PRD template only. Preserve every paragraph, bullet point, CTA, sign-off, "
                    "line break, placeholder replacement, number, and meaning. Do not shorten, summarize, reorder, "
                    "invent, or rewrite the source template."
                ),
            }
            last_error = ""
            sender_attempted = False
            base_custom_prompt = str(payload.get("customPrompt") or "").strip()
            correction_prompt = ""
            for attempt in range(1, 4):
                try:
                    if target_language != "en":
                        payload["customPrompt"] = base_custom_prompt + correction_prompt
                        translated = await self.email_agent(payload)
                        subject = str(translated.get("subject") or "").strip()
                        translated_segments = translated.get("translatedSegments")
                        if translated_segments is not None:
                            if not all(isinstance(item, dict) for item in translated_segments):
                                raise RuntimeError("Structured translation returned invalid segment items.")
                            segment_ids = [str(item.get("id") or "") for item in translated_segments]
                            if len(segment_ids) != len(set(segment_ids)):
                                raise RuntimeError("Structured translation returned duplicate segment ids.")
                            translated_map = {
                                str(item["id"]): str(item.get("text") or item.get("translatedText") or item.get("translated_text") or "")
                                for item in translated_segments
                                if item.get("id")
                            }
                            body = reassemble_translation_segments(source_segments, translated_map)
                        else:
                            if payload.get("structuredTranslation"):
                                raise RuntimeError("Structured translation did not return translatedSegments.")
                            body = str(translated.get("body") or "")
                        body = append_sales_signature(body, config.sales_name)
                        if not subject or not body:
                            raise RuntimeError("Template translation returned an incomplete email.")
                        _validate_complete_translation(
                            source_subject=source_subject,
                            source_body=source_body,
                            translated_subject=subject,
                            translated_body=body,
                            candidate=candidate,
                            sales_name=config.sales_name,
                        )
                    sender_attempted = True
                    delivery = await self.sender({
                        **payload,
                        "subject": subject,
                        "body": body,
                        "purpose": "first_touch",
                    })
                    message_id = str(
                        delivery.get("messageId")
                        or delivery.get("providerMessageId")
                        or (delivery.get("record") or {}).get("messageId")
                        or ""
                    ).strip()
                    if not message_id:
                        raise RuntimeError("SMTP submission returned no Message-ID; delivery cannot be tracked.")
                    self.store.mark_success(run_id=run_id, company_id=company_id, contact_id=contact_id, message_id=message_id)
                    return {"companyId": company_id, "status": "sent", "messageId": message_id, "attempts": attempt}
                except Exception as exc:
                    last_error = str(exc)
                    if target_language != "en" and not sender_attempted:
                        correction_prompt = _translation_correction_prompt(last_error)
                    existing_message_id = self.store.find_existing_delivery(
                        company_id=company_id,
                        contact_id=contact_id,
                    )
                    if existing_message_id:
                        self.store.mark_success(
                            run_id=run_id,
                            company_id=company_id,
                            contact_id=contact_id,
                            message_id=existing_message_id,
                        )
                        return {"companyId": company_id, "status": "sent", "messageId": existing_message_id, "attempts": attempt}
                    if sender_attempted:
                        break
                    if attempt < 3:
                        await asyncio.sleep(2 ** (attempt - 1))
            if target_language != "en" and not sender_attempted:
                try:
                    fallback_body = append_sales_signature(source_body, config.sales_name)
                    delivery = await self.sender({
                        **payload,
                        "subject": source_subject,
                        "body": fallback_body,
                        "purpose": "first_touch",
                        "translationFallback": "source_template",
                    })
                    fallback_message_id = str(
                        delivery.get("messageId")
                        or delivery.get("providerMessageId")
                        or (delivery.get("record") or {}).get("messageId")
                        or ""
                    ).strip()
                    if not fallback_message_id:
                        raise RuntimeError("SMTP submission returned no Message-ID for source-template fallback.")
                    self.store.mark_success(run_id=run_id, company_id=company_id, contact_id=contact_id, message_id=fallback_message_id)
                    return {"companyId": company_id, "status": "sent", "messageId": fallback_message_id, "attempts": 3, "translationFallback": "source_template"}
                except Exception as fallback_error:
                    last_error = f"{last_error}; source-template fallback failed: {fallback_error}"
            self.store.mark_failure(run_id=run_id, company_id=company_id, contact_id=contact_id, error=last_error)
            return {
                "companyId": company_id,
                "contactId": contact_id,
                "contactName": candidate.get("contact_name"),
                "recipientEmail": candidate.get("recipient_email"),
                "companyName": candidate.get("company_name"),
                "status": "failed",
                "error": last_error,
                "attempts": 3,
            }

    async def run_once(self, config: AutoTouchConfig, *, run_id: str | None = None) -> dict[str, Any]:
        if not config.enabled:
            return {"status": "disabled", "sent": 0, "failed": 0, "skipped": 0}
        if run_id is None:
            run_id = self.store.start_run(config)
        if not run_id:
            return {"status": "already_running", "sent": 0, "failed": 0, "skipped": 0}
        summary: dict[str, Any] = {
            "status": "completed",
            "runId": run_id,
            "candidates": 0,
            "sent": 0,
            "failed": 0,
            "skipped": 0,
            "details": [],
        }
        try:
            candidates = self.store.find_candidates(config)
            summary["candidates"] = len(candidates)
            semaphore = asyncio.Semaphore(4)
            results = await asyncio.gather(*(
                self._process_candidate(candidate=candidate, config=config, run_id=run_id, semaphore=semaphore)
                for candidate in candidates
            ))
            for result in results:
                summary[result["status"]] += 1
                if result["status"] != "skipped":
                    summary["details"].append(result)
            self.store.finish_run(run_id=run_id, summary=summary)
            return summary
        except Exception as exc:
            self.store.fail_run(run_id=run_id, error=str(exc))
            raise


async def run_email_automation_agent(
    *,
    config: AutoTouchConfig,
    store: OutreachStore,
    email_agent: EmailAgentRunner,
    sender: EmailSender,
    run_id: str | None = None,
) -> dict[str, Any]:
    return await EmailAutomationAgent(store=store, email_agent=email_agent, sender=sender).run_once(config, run_id=run_id)
