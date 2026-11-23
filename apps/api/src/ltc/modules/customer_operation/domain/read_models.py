from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


Stage = Literal["assigned", "emailed", "replied", "meeting", "proposal", "won", "lost"]
IntentLevel = Literal["interested", "pricing", "product_question", "not_interested", "unsubscribe", "proposal", "won"]


class Company(BaseModel):
    company_id: str = Field(default_factory=lambda: str(uuid4()))
    company_name: str
    industry: str | None = None
    website: str | None = None
    city: str | None = None
    country: str | None = None
    region: str | None = None
    sales_tier: str | None = None
    icp_score: float | None = None
    icp_grade: str | None = None
    assigned_to: str
    stage: Stage = "assigned"


class Contact(BaseModel):
    contact_id: str = Field(default_factory=lambda: str(uuid4()))
    company_id: str
    name: str
    title: str | None = None
    email: str
    role: str | None = None


class EmailAttachmentRecord(BaseModel):
    attachment_id: str
    filename: str
    content_type: str
    size_bytes: int
    download_url: str


class EmailRecord(BaseModel):
    email_id: str = Field(default_factory=lambda: str(uuid4()))
    company_id: str
    contact_id: str
    direction: Literal["inbound", "outbound"] = "outbound"
    subject: str
    body: str
    purpose: Literal["first_touch", "reply_followup", "meeting_followup"] = "first_touch"
    status: Literal["draft", "sent", "replied", "bounced", "unsubscribed"] = "draft"
    sent_at: datetime | None = None
    reply_content: str | None = None
    replied_at: datetime | None = None
    intent_level: IntentLevel | None = None
    next_action: str | None = None
    from_address: str = ""
    to_address: str = ""
    message_id: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    attachments: list[EmailAttachmentRecord] = Field(default_factory=list)


class MeetingActionItem(BaseModel):
    owner: str
    text: str
    due_date: date | None = None


class MeetingSummary(BaseModel):
    customer_needs: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)
    buying_signals: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    action_items: list[MeetingActionItem] = Field(default_factory=list)
    next_step: str


class MeetingRecord(BaseModel):
    meeting_id: str = Field(default_factory=lambda: str(uuid4()))
    company_id: str
    sales_id: str
    meeting_time: datetime
    audio_url: str
    transcript_status: Literal["pending", "processing", "done", "failed"] = "pending"
    transcript: str | None = None
    summary: MeetingSummary | None = None


class FollowUpTask(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    company_id: str
    sales_id: str
    task_type: Literal["email", "meeting", "proposal"]
    description: str
    due_date: date | None = None
    status: Literal["pending", "in_progress", "done", "cancelled", "overdue"] = "pending"


class CustomerActivity(BaseModel):
    activity_id: str = Field(default_factory=lambda: str(uuid4()))
    company_id: str
    activity_type: Literal[
        "email_sent",
        "email_replied",
        "meeting_completed",
        "task_created",
        "task_completed",
        "task_cancelled",
        "customer_assigned",
        "manual_note",
    ]
    direction: Literal["inbound", "outbound", "internal"] | None = None
    subject: str | None = None
    body: str | None = None
    source_type: Literal["email", "meeting", "task", "system"] = "system"
    source_id: str | None = None
    occurred_at: datetime = Field(default_factory=datetime.utcnow)


class ReplyIntent(BaseModel):
    intent_level: IntentLevel
    next_action: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_quote: str | None = None
    evidence_type: str | None = None


class CustomerOperationResponse(BaseModel):
    data: dict[str, Any]


class OperationDetailResponse(BaseModel):
    company: Company
    contacts: list[Contact]
    emails: list[EmailRecord]
    meetings: list[MeetingRecord]
    tasks: list[FollowUpTask]
    activities: list[CustomerActivity] = Field(default_factory=list)
    stage: Stage


