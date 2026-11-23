-- Keep departed sales leads visible for an explicit management handover.

ALTER TABLE ltc.lead_assignment
    ADD COLUMN IF NOT EXISTS handover_pending boolean NOT NULL DEFAULT false;
ALTER TABLE ltc.lead_assignment
    DROP CONSTRAINT IF EXISTS ck_lead_assignment_handover_pending_shape;

ALTER TABLE ltc.lead_assignment
    ADD CONSTRAINT ck_lead_assignment_handover_pending_shape CHECK (
        handover_pending = false OR status = 'active'
    );

CREATE INDEX IF NOT EXISTS ix_lead_assignment_handover_pending
    ON ltc.lead_assignment (assignee_user_id, lead_id)
    WHERE status = 'active' AND handover_pending = true;

CREATE OR REPLACE FUNCTION ltc.assert_sales_lead_assignment_consistency(p_lead_id uuid)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    lead_allocation_status text;
    lead_owner_user_id uuid;
    lead_assignment_started_at timestamptz;
    lead_required_sales_tier text;
    lead_pool_region_code text;
    active_assignment_count bigint;
    matching_assignment_count bigint;
BEGIN
    SELECT allocation_status, current_owner_user_id, current_assignment_started_at,
           required_sales_tier, pool_region_code
    INTO lead_allocation_status, lead_owner_user_id, lead_assignment_started_at,
         lead_required_sales_tier, lead_pool_region_code
    FROM ltc.sales_lead
    WHERE lead_id = p_lead_id;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    SELECT COUNT(*) FILTER (WHERE la.status = 'active'),
           COUNT(*) FILTER (
               WHERE la.status = 'active'
                 AND la.assignee_user_id = lead_owner_user_id
                 AND la.assigned_at = lead_assignment_started_at
                 AND ua.account_type = 'sales'
                 AND (ua.status IN ('active', 'disabled') OR (ua.status = 'departed' AND la.handover_pending))
                 AND ua.sales_tier = lead_required_sales_tier
                 AND ua.region_code = lead_pool_region_code
           )
    INTO active_assignment_count, matching_assignment_count
    FROM ltc.lead_assignment la
    LEFT JOIN ltc.user_account ua ON ua.user_id = la.assignee_user_id
    WHERE la.lead_id = p_lead_id;

    IF lead_allocation_status = 'claimed' THEN
        IF active_assignment_count <> 1 OR matching_assignment_count <> 1 THEN
            RAISE EXCEPTION 'claimed lead % must have exactly one matching active assignment', p_lead_id;
        END IF;
    ELSIF active_assignment_count <> 0 THEN
        RAISE EXCEPTION 'non-claimed lead % cannot have an active assignment', p_lead_id;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION ltc.enforce_user_assignment_consistency()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    assigned_lead_id uuid;
BEGIN
    IF NEW.status = 'departed' AND EXISTS (
        SELECT 1
        FROM ltc.lead_assignment
        WHERE assignee_user_id = NEW.user_id
          AND status = 'active'
          AND handover_pending = false
    ) THEN
        RAISE EXCEPTION 'departed user % can retain only handover-pending assignments', NEW.user_id;
    END IF;

    FOR assigned_lead_id IN
        SELECT lead_id
        FROM ltc.lead_assignment
        WHERE assignee_user_id = NEW.user_id AND status = 'active'
    LOOP
        PERFORM ltc.assert_sales_lead_assignment_consistency(assigned_lead_id);
    END LOOP;

    RETURN NULL;
END;
$$;

-- Backfill rows created by the previous immediate-release departure flow only
-- after the replacement consistency functions are active.
UPDATE ltc.lead_assignment la
SET handover_pending = true
FROM ltc.user_account ua
WHERE ua.user_id = la.assignee_user_id
  AND ua.status = 'departed'
  AND la.status = 'active';
