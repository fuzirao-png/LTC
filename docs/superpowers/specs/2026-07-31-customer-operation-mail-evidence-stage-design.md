# Customer Operation Mail Evidence Stage Design

## Goal

Replace the customer-operation card's task- and CRM-derived proposal/won stages with an evidence-driven email workflow. Incoming and outgoing email bodies and supported attachments can provide proposal or won evidence, and the card advances directly to the highest detected event.

## Confirmed Product Rules

- The card may jump directly to the highest detected stage; earlier stages do not block advancement.
- A request such as “please send a proposal” is not proposal evidence.
- Proposal evidence requires actual proposal content, multiple concrete options, a formal offer, a pricing plan, or explicit confirmation of a specific proposal.
- Contract drafts, review requests, and ordinary terms discussion are not won evidence.
- Won evidence requires explicit signing, stamping, acceptance of final terms, or confirmation of cooperation.
- Won evidence may come from either an incoming customer email or an outgoing sales email.
- Incoming attachments must be downloadable from the existing email-history interface.
- The existing email-history layout otherwise remains unchanged.

## Intent Model

The incoming reply classifier supports exactly seven values:

1. `interested`
2. `pricing`
3. `product_question`
4. `not_interested`
5. `unsubscribe`
6. `proposal`
7. `won`

The classifier evaluates the subject, body, and extracted attachment text. It returns a next action and structured evidence identifying whether the result came from the body or one or more attachments.

Outgoing messages do not need general customer-reply classification. They run the same semantic evidence detector, but only `proposal` and `won` results affect customer-operation progress.

Classification precedence must protect business-critical outcomes:

- Explicit unsubscribe language still activates suppression for incoming replies.
- `won` requires explicit completion language, not the presence of contract vocabulary alone.
- `proposal` requires actual proposal substance or confirmation, not a request for a proposal.
- Existing positive, negative, pricing, and product intents retain their current behavior except that they no longer create stage-driving follow-up tasks.

## Attachment Ingestion

### Incoming Email

The IMAP parser must collect attachment metadata and bytes instead of skipping MIME parts with an attachment disposition. Each attachment is persisted and linked to its email through the existing `ltc.media_asset` and `ltc.email_attachment` tables.

All incoming attachments are retained for authorized download. Semantic extraction is supported for PDF, DOCX, TXT, and XLSX. Unsupported formats remain downloadable but do not contribute extracted text to classification.

### Outgoing Email

The existing outbound attachment flow continues to send and register attachments. The implementation must ensure the persisted media asset has retrievable bytes, then extract supported document text for proposal/won evidence detection.

### Extraction Safety

- Treat attachment filenames as untrusted input.
- Store files under generated storage keys, never directly under user-provided paths.
- Enforce configurable per-file and per-message size limits.
- Extraction failures must not prevent the email from being saved.
- Record extraction failure metadata and continue classifying the remaining content.

## Progress Evidence

The customer-operation card uses the highest available evidence:

| Stage | Evidence | Progress |
|---|---|---:|
| `assigned` | Customer exists | 8.5% |
| `emailed` | At least one outbound email exists | 25% |
| `replied` | At least one inbound email exists | 42% |
| `meeting` | At least one meeting exists | 58.5% |
| `proposal` | Any inbound or outbound email has validated proposal evidence | 75.5% |
| `won` | Any inbound or outbound email has validated won evidence | 100% |

The highest evidence wins immediately. A proposal email may advance a customer from assigned directly to proposal. A signed agreement may advance a customer directly to won.

Stage dates use the earliest timestamp for the matching evidence. Proposal and won dates come from email evidence, not follow-up tasks or CRM stage transitions.

## Removed Customer-Operation Coupling

Remove the following behavior from customer-operation progress:

- Positive reply intents automatically creating follow-up tasks.
- A `proposal` follow-up task advancing the card to proposal.
- A CRM `won` stage transition advancing the card to won.
- A pending task counting as proof that a proposal was actually sent or confirmed.

The sales CRM pipeline remains available for its own workflows, but customer-operation card progress no longer reads proposal/won evidence from it.

## Persistence

`email_message.intent_level` stores the selected seven-value intent when applicable. `email_message.intent_payload` stores structured classifier output including the selected intent, next action, evidence direction, evidence source, concise reason, and attachment extractor status.

Attachment metadata stays in `ltc.email_attachment` and `ltc.media_asset`. File bytes are stored through a local attachment storage adapter using generated storage keys. No credentials or absolute developer-machine paths are persisted.

Do not rewrite distributed migration `0001`. If an additional database column or constraint is required, add a new numbered migration.

## Download API

Add an authenticated download endpoint scoped by company, email, and attachment identifiers. Before returning bytes, verify:

- the current user is authenticated;
- the current sales user may view the company;
- the email belongs to that company and current sales owner scope;
- the attachment belongs to that email;
- the resolved storage path stays inside the configured attachment root.

Return the stored MIME type and a safe `Content-Disposition` filename. The email-history API includes attachment metadata only and never embeds attachment bytes.

## Frontend

The card progress bar uses the exact percentages defined above. Completed nodes are determined by stage rank, not by comparing `index * 20` against the percentage.

The existing history list and read-only preview remain unchanged. For an inbound email with attachments, display a compact attachment list containing filename, formatted size, and a download link or button.

Do not add an intent label, next-action panel, or evidence explanation to the history UI.

## Failure Behavior

- Email storage succeeds even when one attachment cannot be parsed.
- Attachment download returns not found for records outside the user's visibility scope.
- Classifier failure falls back to deterministic rules.
- Unsupported attachments are retained and downloadable but ignored for semantic detection.
- Ambiguous contract discussion never advances to won.
- Existing notification creation and mailbox ownership isolation remain intact.

## Test Strategy

Backend tests cover:

- all seven incoming intents;
- proposal requests not being classified as proposal evidence;
- actual proposal content and proposal confirmation being classified as `proposal`;
- draft/review contract language not being classified as `won`;
- explicit signed, stamped, accepted-final-terms, and cooperation-confirmed language being classified as `won`;
- PDF, DOCX, TXT, and XLSX extraction;
- unsupported attachment retention without semantic extraction;
- incoming attachment persistence and authenticated download;
- sales ownership isolation on attachment download;
- outgoing proposal/won evidence;
- removal of automatic positive-intent follow-up task creation;
- proposal and won stages coming only from email evidence;
- direct highest-event stage jumps;
- exact progress values and stage dates.

Frontend verification covers exact percentages, stage-rank node completion, inbound attachment links, absence of links for attachment-free mail, type checking, and production build.

## Out of Scope

- OCR for PNG, JPG, scanned PDF, or other image-only documents.
- Redesigning the email-history screen.
- Displaying intent labels or classifier explanations in history.
- Replacing the sales CRM pipeline.
- Requiring sequential completion of intermediate stages.
