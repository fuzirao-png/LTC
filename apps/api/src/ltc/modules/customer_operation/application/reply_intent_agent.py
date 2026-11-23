import asyncio
import logging
from typing import Any

from ltc.platform.config import get_settings
from ltc.modules.customer_operation.infrastructure.llm_adapter import LlmClient
from ltc.modules.customer_operation.domain.read_models import ReplyIntent


_logger = logging.getLogger(__name__)


ALLOWED_INTENTS = {
    "interested",
    "pricing",
    "product_question",
    "not_interested",
    "unsubscribe",
    "proposal",
    "won",
}

_PROPOSAL_REQUEST_MARKERS = (
    "please send", "could you send", "please provide", "can you provide",
    "请发送", "请提供", "能否提供", "给我发送",
)
_PROPOSAL_TERMS = (
    "方案一", "方案二", "方案三", "option 1", "option 2",
    "proposal includes", "proposed package", "正式提案", "报价方案",
    "定价方案", "实施方案", "交付方案", "方案没问题", "方案可行",
    "方案完全没问题", "方案没有问题", "方案完全可行",
    "同意该方案", "同意方案", "确认采用", "确认选择",
    "accept the proposal", "approve the proposal",
    "proposal looks good", "proposal is fine", "proceed with the proposal",
)
_WON_TERMS = (
    "合同已签署", "协议已签署", "双方已签署", "完成签署",
    "合同已盖章", "协议已盖章", "双方已盖章", "完成盖章", "完成合同盖章", "完成协议盖章",
    "接受最终条款", "同意最终条款",
    "contract has been signed", "agreement has been signed",
    "fully executed agreement", "signed and stamped",
    "accepted the final terms", "accept the final terms",
)
_WON_NEGATIVE_TERMS = (
    "合同草案", "协议草案", "draft contract", "draft agreement",
    "请审阅", "please review", "suggest changes", "条款讨论", "terms discussion",
)

_PROPOSAL_EVIDENCE_TYPES = {
    "proposal_content",
    "proposal_confirmation",
    "selected_option",
}
_WON_EVIDENCE_TYPES = {
    "signed_contract",
    "final_terms",
}


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def classify_progress_evidence(content: str) -> ReplyIntent | None:
    text = content.lower()
    if _contains_any(text, _WON_TERMS) and not _contains_any(text, _WON_NEGATIVE_TERMS):
        return ReplyIntent(
            intent_level="won",
            next_action="Record the confirmed deal and prepare customer handoff.",
        )
    proposal_request_only = _contains_any(text, _PROPOSAL_REQUEST_MARKERS)
    if _contains_any(text, _PROPOSAL_TERMS) and not proposal_request_only:
        return ReplyIntent(
            intent_level="proposal",
            next_action="Track the proposal and confirm the selected option.",
        )
    return None


def _classify_reply_by_rules(reply_content: str) -> ReplyIntent:
    text = reply_content.lower()
    progress_evidence = classify_progress_evidence(reply_content)
    if progress_evidence is not None:
        return progress_evidence
    if any(word in text for word in ["unsubscribe", "do not contact", "stop", "退订", "拒收", "不要联系"]):
        return ReplyIntent(intent_level="unsubscribe", next_action="Stop further outreach to this contact.")
    if any(word in text for word in ["price", "pricing", "quote", "cost", "费用", "价格", "报价"]):
        return ReplyIntent(intent_level="pricing", next_action="Send pricing deck and schedule a 30-minute pricing discussion.")
    if any(word in text for word in ["product", "coverage", "api", "feature", "产品", "覆盖", "接口"]):
        return ReplyIntent(intent_level="product_question", next_action="Reply with product details and propose a technical discussion.")
    if any(word in text for word in ["interested", "sounds good", "meeting", "demo", "有兴趣", "会议", "演示"]):
        return ReplyIntent(intent_level="interested", next_action="Suggest a meeting and prepare a pilot agenda.")
    return ReplyIntent(intent_level="not_interested", next_action="Mark as low priority and pause active follow-up.")


async def _classify_reply_by_llm(reply_content: str) -> ReplyIntent:
    result = await LlmClient().chat_json(
        system_prompt=(
            "You classify the latest customer-authored sales email reply. Ignore quoted earlier messages, "
            "signatures, and the salesperson's text. Return JSON only with these fields: "
            "intent_level, next_action, confidence, evidence_quote, evidence_type. "
            "intent_level must be one of: interested, pricing, product_question, not_interested, unsubscribe, "
            "proposal, won. Use proposal only for actual proposal substance, concrete options, a formal offer, "
            "or explicit proposal confirmation; a request for a proposal is not proposal. Use won only for "
            "explicit signing, stamping, or final-term acceptance; drafts, review "
            "requests, and terms discussion are not won. Approval of a plan, proposal, package, or version "
            "or a general willingness to cooperate without an explicit signed contract or final-term acceptance is still "
            "proposal, even when the customer says it looks good or to proceed. confidence must be a number "
            "from 0 to 1. "
            "For proposal or won, evidence_quote must be an exact, non-empty span copied from the latest "
            "customer reply and evidence_type must be one of proposal_content, proposal_confirmation, "
            "selected_option, signed_contract, final_terms, confirmed_cooperation. For other intents, "
            "evidence_quote may be empty and evidence_type may be null."
        ),
        user_prompt=f"Customer reply:\n{reply_content}",
    )
    intent_level = str(result.get("intent_level") or "").strip()
    next_action = str(result.get("next_action") or "").strip()
    if intent_level not in ALLOWED_INTENTS or not next_action:
        raise RuntimeError("LLM returned invalid reply intent.")
    confidence_raw = result.get("confidence")
    try:
        confidence = float(confidence_raw) if confidence_raw not in (None, "") else None
    except (TypeError, ValueError) as exc:
        raise RuntimeError("LLM returned invalid confidence.") from exc
    if confidence is not None and not 0 <= confidence <= 1:
        raise RuntimeError("LLM returned invalid confidence.")

    evidence_quote = str(result.get("evidence_quote") or "").strip() or None
    evidence_type = str(result.get("evidence_type") or "").strip() or None
    if intent_level in {"proposal", "won"}:
        if not evidence_quote:
            raise RuntimeError("LLM returned progress intent without evidence quote.")
        normalized_reply = " ".join(reply_content.casefold().split())
        normalized_quote = " ".join(evidence_quote.casefold().split())
        if not normalized_quote or normalized_quote not in normalized_reply:
            raise RuntimeError("LLM returned evidence that is not present in the customer reply.")
        allowed_types = _PROPOSAL_EVIDENCE_TYPES if intent_level == "proposal" else _WON_EVIDENCE_TYPES
        if evidence_type not in allowed_types:
            raise RuntimeError("LLM returned invalid progress evidence type.")

    # A model may interpret general willingness to cooperate as a closed deal.
    # Require deterministic signing, stamping, or final-term evidence for won.
    if intent_level == "won":
        validated = classify_progress_evidence(reply_content)
        if validated is None or validated.intent_level != "won":
            if validated is not None and validated.intent_level == "proposal":
                return ReplyIntent(
                    intent_level="proposal",
                    next_action=validated.next_action,
                    confidence=confidence,
                    evidence_quote=evidence_quote,
                    evidence_type="proposal_confirmation",
                )
            raise RuntimeError("LLM returned won without hard closing evidence.")

    return ReplyIntent(
        intent_level=intent_level,
        next_action=next_action,
        confidence=confidence,
        evidence_quote=evidence_quote,
        evidence_type=evidence_type,
    )


def _run_llm_classifier(reply_content: str) -> ReplyIntent | None:
    settings = get_settings()
    if not settings.llm_api_key:
        return None
    try:
        return asyncio.run(_classify_reply_by_llm(reply_content))
    except RuntimeError as exc:
        if "asyncio.run() cannot be called from a running event loop" in str(exc):
            _logger.warning("reply intent LLM skipped inside an active event loop")
        else:
            _logger.warning("reply intent LLM response rejected; using fallback rules: %s", exc)
        return None
    except Exception as exc:
        _logger.warning("reply intent LLM unavailable; using fallback rules: %s", exc)
        return None


def classify_reply(reply_content: str) -> ReplyIntent:
    llm_intent = _run_llm_classifier(reply_content)
    if llm_intent is not None:
        return llm_intent
    return _classify_reply_by_rules(reply_content)
