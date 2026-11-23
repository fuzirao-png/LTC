-- Allow test accounts to share a mailbox address while retaining one mailbox per user.
ALTER TABLE ltc.user_mailbox
    DROP CONSTRAINT IF EXISTS uq_user_mailbox_email;
