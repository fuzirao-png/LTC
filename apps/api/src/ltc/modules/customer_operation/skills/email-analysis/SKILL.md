---
name: email-analysis
description: Use when analyzing inbound customer-operation email, including customer replies, automatic replies, delivery notifications, and provider notices that may need association with an earlier outreach email.
---

# Email Analysis

Analyze every newly received email before customer-operation side effects are applied.

## Rules

- Classify customer replies, automatic replies, delivery notifications, provider notices, and unknown messages.
- Count automatic replies as replies, but keep the `automatic_reply` category so downstream automation can distinguish them.
- Prefer deterministic DSN evidence over model inference for recipients, SMTP status, bounce type, original subject, and delivery state.
- Do not mark a message delivered or bounced when the status is unknown.
- Return extracted evidence needed to associate an official mailbox notification with its original outbound email and contact.
- Use reply intent analysis for genuine customer replies.

## Output

Return `messageCategory`, `countsAsReply`, `intentLevel`, `nextAction`, `confidence`, `evidenceQuote`, `deliveryStatus`, `bounceType`, `recipients`, `messageIds`, `originalSubject`, and `reason`.
