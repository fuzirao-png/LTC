from datetime import datetime, timezone

from ltc.modules.customer_operation.infrastructure.postgres_customer_home_card_store import (
    _display_name,
    _progress_from_stage,
    _stage_from_dates,
)


def test_customer_operation_progress_uses_requested_percentages() -> None:
    assert _progress_from_stage("assigned") == 8.5
    assert _progress_from_stage("emailed") == 25
    assert _progress_from_stage("replied") == 42
    assert _progress_from_stage("meeting") == 58.5
    assert _progress_from_stage("proposal") == 75.5
    assert _progress_from_stage("won") == 100


def test_highest_email_evidence_can_skip_intermediate_stages() -> None:
    now = datetime(2026, 7, 31, tzinfo=timezone.utc)

    assert _stage_from_dates(won_at=None, proposal_at=now, meeting_at=None, replied_at=None, emailed_at=None) == "proposal"
    assert _stage_from_dates(won_at=now, proposal_at=None, meeting_at=None, replied_at=None, emailed_at=None) == "won"


def test_customer_display_name_prefers_legal_name_and_filters_placeholders() -> None:
    assert _display_name("Pacific TMC Japan Ltd.", "Pacific TMC Japan") == "Pacific TMC Japan Ltd."
    assert _display_name("待确认", "Pacific TMC Japan") == "Pacific TMC Japan"
    assert _display_name("https://acme.com", "sales@acme.com", "acme.com") == ""
