from __future__ import annotations


def sales_visible_company_clause(company_alias: str = "c") -> str:
    """Return the shared SQL predicate for customers visible to a sales user."""
    return f"""
    AND (
        EXISTS (
            SELECT 1 FROM ltc.customer_operation_owner coo
            WHERE coo.company_id = {company_alias}.company_id
              AND coo.sales_user_id = %s
        )
        OR EXISTS (
            SELECT 1 FROM ltc.sales_lead sl
            WHERE sl.company_id = {company_alias}.company_id
              AND sl.current_owner_user_id = %s
              AND sl.allocation_status = 'claimed'
        )
    )
    """


def sales_visible_company_params(owner_user_id: str) -> tuple[str, str]:
    return owner_user_id, owner_user_id


def clean_customer_company_clause(company_alias: str = "c") -> str:
    """Exclude placeholder and domain-derived rows from customer-facing panels."""
    return f"""
    AND btrim(COALESCE({company_alias}.company_name, '')) <> ''
    AND lower(btrim({company_alias}.company_name)) NOT IN (
        '待确认', '待补齐', '未知', 'unknown', 'n/a', '-'
    )
    AND btrim({company_alias}.company_name) !~* '^[^[:space:]@]+\\.(com|net|org|io|co|cn|jp|kr)$'
    """
