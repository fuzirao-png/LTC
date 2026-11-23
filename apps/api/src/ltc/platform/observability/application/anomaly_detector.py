"""Anomaly detection engine — P1-P4 severity classification per v3.3 spec.

Detects anomalies by querying the database for deviation from baselines.
Runs as a periodic job (``platform.detect_anomalies.v1``) dispatched by the worker.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

Severity = str  # "P1" | "P2" | "P3" | "P4"


@dataclass(slots=True)
class Anomaly:
    severity: Severity
    category: str  # system | business | data_quality | ai_quality
    title: str
    detail: str
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    related_entity_type: str | None = None
    related_entity_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# Detection engine
# ---------------------------------------------------------------------------


class AnomalyDetector:
    """Runs all detection rules against the database and returns active anomalies.

    Each check_X method returns a list of Anomaly objects. Empty list = healthy.
    """

    def __init__(self, db: object, emitter: object | None = None) -> None:
        self._db = db
        self._emitter = emitter

    def run_all(self) -> list[Anomaly]:
        results: list[Anomaly] = []
        results.extend(self.check_system_health())
        results.extend(self.check_business_health())
        results.extend(self.check_data_quality())
        results.extend(self.check_ai_quality())
        return results

    # -- P1: System health (immediate alert) -------------------------------

    def check_system_health(self) -> list[Anomaly]:
        anomalies: list[Anomaly] = []
        anomalies.extend(self._check_llm_availability())
        anomalies.extend(self._check_worker_heartbeat())
        anomalies.extend(self._check_spam_complaint_rate())
        return anomalies

    def _check_llm_availability(self) -> list[Anomaly]:
        # If 3+ consecutive AI events in last 5 min all failed, trigger P1
        try:
            with self._db._connection() as conn:
                row = conn.execute(
                    """SELECT count(*) AS consecutive_failures
                       FROM (
                           SELECT success,
                                  row_number() OVER (ORDER BY occurred_at DESC) AS rn
                           FROM ltc.ai_event
                           WHERE occurred_at > now() - interval '5 minutes'
                           ORDER BY occurred_at DESC
                       ) sub
                       WHERE success = false AND rn <= 3""",
                ).fetchone()
                if row and row[0] >= 3:
                    return [Anomaly("P1", "system", "LLM 连续调用失败", f"最近 5 分钟内连续 {row[0]} 次 LLM 调用失败")]
        except Exception:
            pass
        return []

    def _check_worker_heartbeat(self) -> list[Anomaly]:
        # If no job completed in last 10 minutes
        try:
            with self._db._connection() as conn:
                row = conn.execute(
                    "SELECT count(*) FROM ltc.job WHERE completed_at > now() - interval '10 minutes'",
                ).fetchone()
                if row and row[0] == 0:
                    return [Anomaly("P1", "system", "Worker 心跳超时", "最近 10 分钟无任务完成，Worker 可能已停止")]
        except Exception:
            pass
        return []

    def _check_spam_complaint_rate(self) -> list[Anomaly]:
        try:
            with self._db._connection() as conn:
                row = conn.execute(
                    """SELECT count(*) FILTER (WHERE event_code = 'email.spam_complaint') AS complaints,
                              count(*) FILTER (WHERE event_code = 'email.sent') AS total
                       FROM ltc.lead_lifecycle_event
                       WHERE occurred_at > now() - interval '7 days'""",
                ).fetchone()
                if row and row[1] > 0 and (row[0] / row[1]) > 0.001:
                    return [Anomaly("P1", "system", "垃圾投诉率超过 0.1%", f"7 天内投诉 {row[0]} 次，发送 {row[1]} 封")]
        except Exception:
            pass
        return []

    # -- P2: Business health (1h response) ---------------------------------

    def check_business_health(self) -> list[Anomaly]:
        anomalies: list[Anomaly] = []
        anomalies.extend(self._check_bounce_rate())
        anomalies.extend(self._check_conversion_drop())
        anomalies.extend(self._check_ai_adoption_drop())
        return anomalies

    def _check_bounce_rate(self) -> list[Anomaly]:
        try:
            with self._db._connection() as conn:
                row = conn.execute(
                    """SELECT count(*) FILTER (WHERE event_code = 'email.bounced') AS bounced,
                              count(*) FILTER (WHERE event_code = 'email.sent') AS total
                       FROM ltc.lead_lifecycle_event
                       WHERE occurred_at > now() - interval '7 days'""",
                ).fetchone()
                if row and row[1] > 0 and (row[0] / row[1]) > 0.15:
                    return [Anomaly("P2", "business", "退信率超过 15%", f"7 天内退信 {row[0]} 封 / 发送 {row[1]} 封")]
        except Exception:
            pass
        return []

    def _check_conversion_drop(self) -> list[Anomaly]:
        try:
            with self._db._connection() as conn:
                row = conn.execute(
                    """WITH this_month AS (
                           SELECT count(*) FILTER (WHERE event_code = 'deal.won') AS won,
                                  count(*) FILTER (WHERE event_code = 'lead.assigned') AS assigned
                           FROM ltc.lead_lifecycle_event
                           WHERE occurred_at > date_trunc('month', now())
                       ), last_month AS (
                           SELECT count(*) FILTER (WHERE event_code = 'deal.won') AS won,
                                  count(*) FILTER (WHERE event_code = 'lead.assigned') AS assigned
                           FROM ltc.lead_lifecycle_event
                           WHERE occurred_at BETWEEN date_trunc('month', now() - interval '1 month')
                                                 AND date_trunc('month', now())
                       )
                       SELECT CASE WHEN lm.assigned > 0 THEN lm.won::float / lm.assigned END AS lm_rate,
                              CASE WHEN tm.assigned > 0 THEN tm.won::float / tm.assigned END AS tm_rate
                       FROM this_month tm, last_month lm""",
                ).fetchone()
                if row and row[0] and row[1] and row[1] > 0 and (row[1] / row[0]) < 0.7:
                    return [Anomaly("P2", "business", "转化率较上月下降超过 30%", f"上月 {row[0]:.2%}, 本月 {row[1]:.2%}")]
        except Exception:
            pass
        return []

    def _check_ai_adoption_drop(self) -> list[Anomaly]:
        try:
            with self._db._connection() as conn:
                row = conn.execute(
                    """SELECT count(*) FILTER (WHERE success) AS successes,
                              count(*) AS total
                       FROM ltc.ai_event
                       WHERE occurred_at > now() - interval '30 days'""",
                ).fetchone()
        except Exception:
            pass
        return []

    # -- P3: Data quality (4h response) ------------------------------------

    def check_data_quality(self) -> list[Anomaly]:
        anomalies: list[Anomaly] = []
        anomalies.extend(self._check_stale_leads())
        anomalies.extend(self._check_single_source_dominance())
        return anomalies

    def _check_stale_leads(self) -> list[Anomaly]:
        try:
            with self._db._connection() as conn:
                row = conn.execute(
                    """SELECT count(*) FROM ltc.sales_lead
                       WHERE allocation_status = 'claimed'
                         AND (SELECT max(occurred_at) FROM ltc.lead_lifecycle_event
                              WHERE lead_id = sales_lead.lead_id
                                AND event_code = 'email.sent')
                             < now() - interval '14 days'""",
                ).fetchone()
                if row and row[0] > 10:
                    return [Anomaly("P3", "data_quality", "多条线索 14 天无活动", f"{row[0]} 条线索超过 14 天无邮件发送")]
        except Exception:
            pass
        return []

    def _check_single_source_dominance(self) -> list[Anomaly]:
        try:
            with self._db._connection() as conn:
                row = conn.execute(
                    """SELECT provider, count(*) AS cnt
                       FROM ltc.tool_event
                       WHERE occurred_at > now() - interval '7 days'
                       GROUP BY provider""",
                ).fetchall()
                total = sum(r[1] for r in row)
                if total > 100:
                    for provider, cnt in row:
                        if cnt / total > 0.8:
                            return [Anomaly("P3", "data_quality", "单一数据源占比超过 80%", f"{provider} 占 {cnt}/{total} ({cnt/total:.0%})")]
        except Exception:
            pass
        return []

    # -- P4: AI quality (24h response) -------------------------------------

    def check_ai_quality(self) -> list[Anomaly]:
        anomalies: list[Anomaly] = []
        anomalies.extend(self._check_low_confidence_rate())
        anomalies.extend(self._check_first_draft_availability())
        return anomalies

    def _check_low_confidence_rate(self) -> list[Anomaly]:
        try:
            with self._db._connection() as conn:
                row = conn.execute(
                    """SELECT count(*) FILTER (WHERE confidence < 70) AS low_conf,
                              count(*) AS total
                       FROM ltc.ai_event
                       WHERE confidence IS NOT NULL
                         AND occurred_at > now() - interval '7 days'""",
                ).fetchone()
                if row and row[1] > 20 and (row[0] / row[1]) > 0.5:
                    return [Anomaly("P4", "ai_quality", "AI 低置信率超过 50%", f"7 天内 {row[0]}/{row[1]} 次调用 confidence < 70")]
        except Exception:
            pass
        return []

    def _check_first_draft_availability(self) -> list[Anomaly]:
        # Placeholder - requires email interaction tracking from frontend
        return []
