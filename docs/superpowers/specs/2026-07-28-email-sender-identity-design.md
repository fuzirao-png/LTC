# Email Sender Identity Design

## Problem

Inbound notifications contain the real sender address, and the database links each email to the correct contact. The customer-operation email-history response drops the message addresses and Message-ID, so the frontend creates an example address from the company name and cannot select the sender associated with the notification target.

## Design

Extend each email-history item with `from_address`, `to_address`, `message_id`, `contact_name`, and `contact_email`. Keep the existing fields unchanged for compatibility.

The frontend will build inbound sender nodes from those real fields, match notification targets by email ID or Message-ID, and synchronize the selected contact whenever a targeted or manually selected inbound email is opened. Example addresses will no longer be generated.

## Verification

- Backend route tests assert seeded inbound and outbound address metadata.
- Customer-operation tests continue to pass.
- The web production build passes.
- Browser verification confirms the notification sender and displayed email are identical.
