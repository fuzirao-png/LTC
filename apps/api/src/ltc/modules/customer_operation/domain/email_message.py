from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


EmailDirection = Literal["outbound", "inbound"]
EmailStatus = Literal[
    "draft",
    "sending",
    "sent",
    "delivered",
    "opened",
    "clicked",
    "replied",
    "bounced",
    "failed",
]
EmailIntent = Literal["interested", "pricing", "product_question", "not_interested", "unsubscribe", "proposal", "won"]


@dataclass(frozen=True)
class EmailMessage:
    email_id: UUID
    company_id: UUID
    contact_id: UUID | None
    direction: EmailDirection
    subject: str
    body: str
    status: EmailStatus
    intent_level: EmailIntent | None
    model_name: str | None
    in_reply_to: UUID | None
    version: int
    created_at: datetime
    updated_at: datetime





