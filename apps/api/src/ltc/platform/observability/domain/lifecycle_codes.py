"""Lead lifecycle event codes — EVT-01 through EVT-25 per v3.3 spec."""


class LifecycleCodes:
    """Well-known event_code values for ltc.lead_lifecycle_event."""

    # Candidate lifecycle
    LEAD_FOUND = "lead.found"
    LEAD_ENRICHED = "lead.enriched"
    LEAD_SCENE_RECOGNIZED = "lead.scene_recognized"
    LEAD_CONTACT_MATCHED = "lead.contact_matched"
    LEAD_SCORED = "lead.scored"
    LEAD_DEDUPLICATED = "lead.deduplicated"

    # CRM lifecycle
    LEAD_ASSIGNED = "lead.assigned"
    LEAD_CLAIMED = "lead.claimed"
    LEAD_RELEASED = "lead.released"

    # Engagement
    EMAIL_SENT = "email.sent"
    EMAIL_OPENED = "email.opened"
    EMAIL_CLICKED = "email.clicked"
    EMAIL_REPLIED = "email.replied"
    EMAIL_BOUNCED = "email.bounced"
    EMAIL_UNSUBSCRIBED = "email.unsubscribed"
    EMAIL_SPAM_COMPLAINT = "email.spam_complaint"

    # Meeting
    MEETING_UPLOADED = "meeting.uploaded"
    MEETING_TRANSCRIBED = "meeting.transcribed"
    MEETING_SUMMARIZED = "meeting.summarized"

    # Analysis
    REPORT_GENERATED = "report.generated"

    # Pipeline
    STAGE_MOVED = "stage.moved"
    DEAL_CREATED = "deal.created"
    DEAL_WON = "deal.won"
    DEAL_LOST = "deal.lost"

    # Reactivation
    LEAD_REACTIVATED = "lead.reactivated"
