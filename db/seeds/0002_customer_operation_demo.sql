-- LTC customer-operation demo seed v3.7
-- Purpose: preload a complete customer communication loop for local testing.
-- Safe to run multiple times.

BEGIN;

SET search_path TO ltc, public;

INSERT INTO ltc.user_account (
    user_id,
    username,
    password_hash,
    display_name,
    email,
    account_type,
    sales_tier,
    region_code,
    capacity_limit,
    status
) VALUES (
    '11111111-1111-4111-8111-111111111111',
    'li_ming',
    'demo-only-not-for-login',
    'Li Ming',
    'li.ming@51tgt.com',
    'sales',
    'SA',
    'EA',
    25,
    'active'
)
ON CONFLICT (user_id) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    email = EXCLUDED.email,
    account_type = EXCLUDED.account_type,
    sales_tier = EXCLUDED.sales_tier,
    region_code = EXCLUDED.region_code,
    capacity_limit = EXCLUDED.capacity_limit,
    status = EXCLUDED.status,
    updated_at = clock_timestamp();

INSERT INTO ltc.company (
    company_id,
    company_name,
    normalized_company_name,
    legal_name,
    primary_domain,
    website,
    country_code,
    region_code,
    region_mapping_version,
    city,
    industry_code,
    company_intro,
    employee_count,
    lifecycle_status,
    created_by
) VALUES (
    '22222222-2222-4222-8222-222222222222',
    'Pacific TMC Japan',
    'pacific tmc japan',
    'Pacific TMC Japan Ltd.',
    'pacific-tmc.example.com',
    'https://pacific-tmc.example.com',
    'JP',
    'EA',
    'region-country-v5',
    'Tokyo',
    'TMC',
    'A travel management company evaluating enterprise eSIM coverage, billing visibility, and operational control.',
    320,
    'prospect',
    '11111111-1111-4111-8111-111111111111'
)
ON CONFLICT (company_id) DO UPDATE SET
    company_name = EXCLUDED.company_name,
    normalized_company_name = EXCLUDED.normalized_company_name,
    legal_name = EXCLUDED.legal_name,
    primary_domain = EXCLUDED.primary_domain,
    website = EXCLUDED.website,
    country_code = EXCLUDED.country_code,
    region_code = EXCLUDED.region_code,
    region_mapping_version = EXCLUDED.region_mapping_version,
    city = EXCLUDED.city,
    industry_code = EXCLUDED.industry_code,
    company_intro = EXCLUDED.company_intro,
    employee_count = EXCLUDED.employee_count,
    lifecycle_status = EXCLUDED.lifecycle_status,
    updated_at = clock_timestamp();

INSERT INTO ltc.contact (
    contact_id,
    company_id,
    full_name,
    normalized_name,
    title,
    title_normalized,
    department,
    relationship_role,
    priority,
    primary_email,
    normalized_email,
    email_status,
    email_type,
    email_score,
    source,
    status
) VALUES (
    '33333333-3333-4333-8333-333333333333',
    '22222222-2222-4222-8222-222222222222',
    'James Wilson',
    'james wilson',
    'VP Operations',
    'vp operations',
    'Operations',
    'decision_maker',
    'P1',
    'james@pacific-tmc.example.com',
    'james@pacific-tmc.example.com',
    'valid',
    'business',
    92,
    'operation',
    'active'
)
ON CONFLICT (contact_id) DO UPDATE SET
    company_id = EXCLUDED.company_id,
    full_name = EXCLUDED.full_name,
    normalized_name = EXCLUDED.normalized_name,
    title = EXCLUDED.title,
    title_normalized = EXCLUDED.title_normalized,
    department = EXCLUDED.department,
    relationship_role = EXCLUDED.relationship_role,
    priority = EXCLUDED.priority,
    primary_email = EXCLUDED.primary_email,
    normalized_email = EXCLUDED.normalized_email,
    email_status = EXCLUDED.email_status,
    email_type = EXCLUDED.email_type,
    email_score = EXCLUDED.email_score,
    source = EXCLUDED.source,
    status = EXCLUDED.status,
    updated_at = clock_timestamp();

INSERT INTO ltc.email_message (
    email_id,
    company_id,
    contact_id,
    thread_key,
    direction,
    purpose,
    status,
    from_address,
    intended_to_address,
    delivered_to_address,
    subject,
    body_text,
    generation_prompt_version,
    generation_model,
    provider_code,
    provider_message_id,
    message_id_header,
    idempotency_key,
    sent_at,
    created_at,
    updated_at
) VALUES (
    '44444444-4444-4444-8444-444444444444',
    '22222222-2222-4222-8222-222222222222',
    '33333333-3333-4333-8333-333333333333',
    'demo-thread-pacific-tmc-japan',
    'outbound',
    'first_touch',
    'sent',
    'global.marketing@51tgt.com',
    'james@pacific-tmc.example.com',
    'james@pacific-tmc.example.com',
    'Enterprise eSIM pilot for Pacific TMC Japan',
    'Hi James, we can help Pacific TMC Japan test multi-country eSIM coverage, billing visibility, and operational control. Would you be open to a 30-minute pilot discussion this week?',
    'customer-operation-v3.7-demo',
    'gpt-5.5',
    'smtp',
    '<demo-outbound-pacific-tmc@ltc.local>',
    '<demo-outbound-pacific-tmc@ltc.local>',
    'demo:email:first-touch:pacific-tmc',
    '2026-07-22 09:00:00+08',
    '2026-07-22 09:00:00+08',
    '2026-07-22 09:00:00+08'
)
ON CONFLICT (email_id) DO UPDATE SET
    purpose = EXCLUDED.purpose,
    status = EXCLUDED.status,
    subject = EXCLUDED.subject,
    body_text = EXCLUDED.body_text,
    generation_model = EXCLUDED.generation_model,
    provider_code = EXCLUDED.provider_code,
    provider_message_id = EXCLUDED.provider_message_id,
    updated_at = clock_timestamp();

INSERT INTO ltc.email_delivery_attempt (
    delivery_attempt_id,
    email_id,
    attempt_no,
    provider_code,
    idempotency_key,
    provider_message_id,
    status,
    request_payload,
    response_payload,
    started_at,
    accepted_at,
    completed_at
) VALUES (
    '55555555-5555-4555-8555-555555555555',
    '44444444-4444-4444-8444-444444444444',
    1,
    'smtp',
    'demo:delivery:first-touch:pacific-tmc',
    '<demo-outbound-pacific-tmc@ltc.local>',
    'delivered',
    '{"host":"smtp.exmail.qq.com","port":465,"mode":"demo"}'::jsonb,
    '{"provider":"smtp","deliveredTo":"james@pacific-tmc.example.com"}'::jsonb,
    '2026-07-22 09:00:00+08',
    '2026-07-22 09:00:02+08',
    '2026-07-22 09:00:03+08'
)
ON CONFLICT (delivery_attempt_id) DO UPDATE SET
    status = EXCLUDED.status,
    response_payload = EXCLUDED.response_payload,
    completed_at = EXCLUDED.completed_at;

INSERT INTO ltc.email_message (
    email_id,
    company_id,
    contact_id,
    parent_email_id,
    thread_key,
    direction,
    status,
    from_address,
    intended_to_address,
    delivered_to_address,
    subject,
    body_text,
    intent_level,
    intent_payload,
    next_action,
    provider_code,
    message_id_header,
    in_reply_to,
    received_at,
    created_at,
    updated_at
) VALUES (
    '66666666-6666-4666-8666-666666666666',
    '22222222-2222-4222-8222-222222222222',
    '33333333-3333-4333-8333-333333333333',
    '44444444-4444-4444-8444-444444444444',
    'demo-thread-pacific-tmc-japan',
    'inbound',
    'processed',
    'James Wilson <james@pacific-tmc.example.com>',
    'global.marketing@51tgt.com',
    'global.marketing@51tgt.com',
    'Re: Enterprise eSIM pilot for Pacific TMC Japan',
    'Thanks Li, please send pricing and coverage details for Japan, Singapore, and Europe. A pilot discussion next week sounds useful.',
    'pricing',
    '{"event_type":"email_received","intent_level":"pricing","confidence":"demo"}'::jsonb,
    'Send pricing deck and schedule a 30-minute pricing discussion.',
    'imap',
    '<demo-inbound-pacific-tmc@example.com>',
    '<demo-outbound-pacific-tmc@ltc.local>',
    '2026-07-22 15:30:00+08',
    '2026-07-22 15:30:00+08',
    '2026-07-22 15:30:00+08'
)
ON CONFLICT (email_id) DO UPDATE SET
    status = EXCLUDED.status,
    body_text = EXCLUDED.body_text,
    intent_level = EXCLUDED.intent_level,
    intent_payload = EXCLUDED.intent_payload,
    next_action = EXCLUDED.next_action,
    updated_at = clock_timestamp();

INSERT INTO ltc.follow_up_task (
    task_id,
    company_id,
    source_email_id,
    task_type,
    title,
    description,
    due_at,
    status,
    priority,
    idempotency_key,
    created_by,
    created_at,
    updated_at
) VALUES (
    '77777777-7777-4777-8777-777777777777',
    '22222222-2222-4222-8222-222222222222',
    '66666666-6666-4666-8666-666666666666',
    'email',
    'Follow up: pricing',
    'Send pricing deck and schedule a 30-minute pricing discussion.',
    '2026-07-24 18:00:00+08',
    'pending',
    80,
    'demo:task:pricing:pacific-tmc',
    '11111111-1111-4111-8111-111111111111',
    '2026-07-22 15:31:00+08',
    '2026-07-22 15:31:00+08'
)
ON CONFLICT (task_id) DO UPDATE SET
    title = EXCLUDED.title,
    description = EXCLUDED.description,
    due_at = EXCLUDED.due_at,
    status = EXCLUDED.status,
    priority = EXCLUDED.priority,
    updated_at = clock_timestamp();

INSERT INTO ltc.job (
    job_id,
    job_type,
    queue_name,
    aggregate_type,
    aggregate_id,
    status,
    priority,
    payload,
    result_summary,
    progress_percent,
    attempt_count,
    max_attempts,
    run_after,
    created_by,
    completed_at
) VALUES (
    '88888888-8888-4888-8888-888888888888',
    'meeting_analysis',
    'meeting',
    'company',
    '22222222-2222-4222-8222-222222222222',
    'succeeded',
    100,
    '{"source":"demo-seed"}'::jsonb,
    '{"summary":"Demo meeting completed"}'::jsonb,
    100,
    1,
    5,
    '2026-07-23 10:00:00+08',
    '11111111-1111-4111-8111-111111111111',
    '2026-07-23 10:20:00+08'
)
ON CONFLICT (job_id) DO UPDATE SET
    status = EXCLUDED.status,
    result_summary = EXCLUDED.result_summary,
    progress_percent = EXCLUDED.progress_percent,
    completed_at = EXCLUDED.completed_at,
    updated_at = clock_timestamp();

INSERT INTO ltc.media_asset (
    media_asset_id,
    company_id,
    asset_kind,
    storage_backend,
    storage_key,
    original_filename,
    mime_type,
    size_bytes,
    sha256,
    status,
    validation_payload,
    created_by,
    created_at
) VALUES (
    '99999999-9999-4999-8999-999999999999',
    '22222222-2222-4222-8222-222222222222',
    'meeting_source',
    'local',
    'demo/meetings/pacific-tmc-discovery.m4a',
    'pacific-tmc-discovery.m4a',
    'audio/mp4',
    1024,
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    'ready',
    '{"source":"demo-seed"}'::jsonb,
    '11111111-1111-4111-8111-111111111111',
    '2026-07-23 10:00:00+08'
)
ON CONFLICT (media_asset_id) DO UPDATE SET
    company_id = EXCLUDED.company_id,
    storage_key = EXCLUDED.storage_key,
    original_filename = EXCLUDED.original_filename,
    mime_type = EXCLUDED.mime_type,
    status = EXCLUDED.status,
    validation_payload = EXCLUDED.validation_payload;

INSERT INTO ltc.meeting (
    meeting_id,
    company_id,
    primary_contact_id,
    owner_user_id,
    source_media_asset_id,
    current_job_id,
    title,
    source,
    meeting_started_at,
    duration_seconds,
    processing_status,
    transcript_status,
    transcript_text,
    transcript_language,
    transcript_provider,
    summary_payload,
    summary_prompt_version,
    summary_model,
    created_at,
    updated_at
) VALUES (
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    '22222222-2222-4222-8222-222222222222',
    '33333333-3333-4333-8333-333333333333',
    '11111111-1111-4111-8111-111111111111',
    '99999999-9999-4999-8999-999999999999',
    '88888888-8888-4888-8888-888888888888',
    'Pacific TMC Japan pilot discovery',
    'upload',
    '2026-07-23 10:00:00+08',
    1200,
    'completed',
    'done',
    'Customer asked for pricing, country coverage, billing reconciliation, and a pilot plan.',
    'en',
    'whisper-1',
    '{"customer_needs":["Japan, Singapore, and Europe coverage proof","Billing reconciliation","Pilot pricing"],"pain_points":["Needs transparent pricing and billing control"],"buying_signals":["Customer asked for pricing and pilot discussion"],"action_items":[{"task":"Send pricing deck and pilot plan","owner":"sales","due_at":"2026-07-24T18:00:00+08:00"}],"decisions":["Customer is open to pilot discussion"],"risks":["Needs clear regional coverage proof"],"keywords":["pricing","coverage","billing","pilot"],"next_step":"Send pricing deck and propose pilot plan."}'::jsonb,
    'customer-operation-v3.7-demo',
    'gpt-5.5',
    '2026-07-23 10:20:00+08',
    '2026-07-23 10:20:00+08'
)
ON CONFLICT (meeting_id) DO UPDATE SET
    title = EXCLUDED.title,
    processing_status = EXCLUDED.processing_status,
    transcript_status = EXCLUDED.transcript_status,
    transcript_text = EXCLUDED.transcript_text,
    summary_payload = EXCLUDED.summary_payload,
    summary_model = EXCLUDED.summary_model,
    updated_at = clock_timestamp();

INSERT INTO ltc.meeting_segment (
    company_id,
    meeting_id,
    sequence_no,
    start_seconds,
    end_seconds,
    speaker_id,
    speaker_label,
    speaker_contact_id,
    transcript_text,
    confidence
) VALUES
    (
        '22222222-2222-4222-8222-222222222222',
        'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        1,
        0,
        42,
        'spk_sales',
        'Li Ming',
        NULL,
        'We can start with a focused Japan, Singapore, and Europe eSIM pilot.',
        0.96
    ),
    (
        '22222222-2222-4222-8222-222222222222',
        'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        2,
        42,
        95,
        'spk_customer',
        'James Wilson',
        '33333333-3333-4333-8333-333333333333',
        'Please send pricing, coverage details, and billing reconciliation options.',
        0.94
    )
ON CONFLICT (meeting_id, sequence_no) DO UPDATE SET
    transcript_text = EXCLUDED.transcript_text,
    confidence = EXCLUDED.confidence;

INSERT INTO ltc.follow_up_task (
    task_id,
    company_id,
    source_meeting_id,
    task_type,
    title,
    description,
    due_at,
    status,
    priority,
    idempotency_key,
    created_by,
    created_at,
    updated_at
) VALUES (
    'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    '22222222-2222-4222-8222-222222222222',
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    'proposal',
    'Send pilot pricing deck',
    'Send pricing deck, regional coverage proof, and pilot implementation plan.',
    '2026-07-24 18:00:00+08',
    'pending',
    70,
    'demo:task:meeting-proposal:pacific-tmc',
    '11111111-1111-4111-8111-111111111111',
    '2026-07-23 10:21:00+08',
    '2026-07-23 10:21:00+08'
)
ON CONFLICT (task_id) DO UPDATE SET
    title = EXCLUDED.title,
    description = EXCLUDED.description,
    due_at = EXCLUDED.due_at,
    status = EXCLUDED.status,
    priority = EXCLUDED.priority,
    updated_at = clock_timestamp();

INSERT INTO ltc.customer_activity (
    activity_id,
    company_id,
    activity_type,
    direction,
    subject,
    body,
    actor_user_id,
    source_type,
    source_external_key,
    payload,
    occurred_at
) VALUES
    (
        'cccccccc-0001-4ccc-8ccc-cccccccccccc',
        '22222222-2222-4222-8222-222222222222',
        'system',
        'internal',
        'Customer assigned',
        'Pacific TMC Japan is assigned to Li Ming for first touch.',
        '11111111-1111-4111-8111-111111111111',
        'system',
        'demo:activity:assigned:pacific-tmc',
        '{"event_type":"customer_assigned"}'::jsonb,
        '2026-07-22 08:30:00+08'
    ),
    (
        'cccccccc-0002-4ccc-8ccc-cccccccccccc',
        '22222222-2222-4222-8222-222222222222',
        'system',
        'outbound',
        'Enterprise eSIM pilot for Pacific TMC Japan',
        'First-touch email sent.',
        '11111111-1111-4111-8111-111111111111',
        'system',
        '<demo-outbound-pacific-tmc@ltc.local>',
        '{"event_type":"email_sent","purpose":"first_touch","email_id":"44444444-4444-4444-8444-444444444444"}'::jsonb,
        '2026-07-22 09:00:03+08'
    ),
    (
        'cccccccc-0003-4ccc-8ccc-cccccccccccc',
        '22222222-2222-4222-8222-222222222222',
        'system',
        'inbound',
        'Re: Enterprise eSIM pilot for Pacific TMC Japan',
        'Customer replied and asked for pricing and coverage details.',
        NULL,
        'system',
        '<demo-inbound-pacific-tmc@example.com>',
        '{"event_type":"email_received","intent_level":"pricing","next_action":"Send pricing deck and schedule a 30-minute pricing discussion."}'::jsonb,
        '2026-07-22 15:30:00+08'
    ),
    (
        'cccccccc-0004-4ccc-8ccc-cccccccccccc',
        '22222222-2222-4222-8222-222222222222',
        'system',
        'internal',
        'Follow up: pricing',
        'Pricing follow-up task created from inbound email.',
        '11111111-1111-4111-8111-111111111111',
        'system',
        'demo:activity:task-pricing:pacific-tmc',
        '{"event_type":"task_created","task_id":"77777777-7777-4777-8777-777777777777"}'::jsonb,
        '2026-07-22 15:31:00+08'
    ),
    (
        'cccccccc-0005-4ccc-8ccc-cccccccccccc',
        '22222222-2222-4222-8222-222222222222',
        'system',
        'internal',
        'Pacific TMC Japan pilot discovery',
        'Meeting completed and next step extracted.',
        '11111111-1111-4111-8111-111111111111',
        'system',
        'demo:activity:meeting:pacific-tmc',
        '{"event_type":"meeting_completed","meeting_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","next_step":"Send pricing deck and propose pilot plan."}'::jsonb,
        '2026-07-23 10:20:00+08'
    )
ON CONFLICT (activity_id) DO UPDATE SET
    subject = EXCLUDED.subject,
    body = EXCLUDED.body,
    payload = EXCLUDED.payload,
    occurred_at = EXCLUDED.occurred_at;

INSERT INTO ltc.manual_note (
    note_id,
    company_id,
    sales_id,
    raw_text,
    extracted_fields_json,
    confirm_status,
    created_at,
    updated_at
) VALUES (
    'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
    '22222222-2222-4222-8222-222222222222',
    '11111111-1111-4111-8111-111111111111',
    'Customer cares most about coverage proof, pricing transparency, and billing reconciliation.',
    '[{"field":"need","value":"coverage proof"},{"field":"need","value":"pricing transparency"},{"field":"need","value":"billing reconciliation"}]'::jsonb,
    'confirmed',
    '2026-07-23 10:25:00+08',
    '2026-07-23 10:25:00+08'
)
ON CONFLICT (note_id) DO UPDATE SET
    raw_text = EXCLUDED.raw_text,
    extracted_fields_json = EXCLUDED.extracted_fields_json,
    confirm_status = EXCLUDED.confirm_status,
    updated_at = clock_timestamp();

UPDATE ltc.company
SET industry_code = 'OTHER',
    updated_at = clock_timestamp()
WHERE industry_code IS NULL
  AND lower(trim(primary_domain)) IN ('qq.com', '51tgt.com', 'exmail.weixin.qq.com');

COMMIT;
