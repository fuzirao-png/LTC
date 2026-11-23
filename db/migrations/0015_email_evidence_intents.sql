ALTER TABLE ltc.email_message
    DROP CONSTRAINT IF EXISTS ck_email_message_intent_level;

ALTER TABLE ltc.email_message
    ADD CONSTRAINT ck_email_message_intent_level
    CHECK (
        intent_level IS NULL OR intent_level IN (
            'interested',
            'pricing',
            'product_question',
            'not_interested',
            'unsubscribe',
            'proposal',
            'won'
        )
    );
