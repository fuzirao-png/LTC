"""Job service platform package.

Provides a thin helper to enrich job payloads with the current request
trace-id so the Worker Runtime can propagate it into every log record
emitted during job execution.  Business modules call ``inject_trace_id()``
when they build the job creation payload.
"""

from __future__ import annotations

from typing import Any

# Key that the worker runtime reads from job.payload.
TRACE_ID_PAYLOAD_KEY = "_trace_id"


def inject_trace_id(payload: dict[str, Any]) -> dict[str, Any]:
    """Copy *payload*, injecting the current HTTP trace-id.

    Usage in a business module::

        from ltc.platform.jobs import inject_trace_id
        from ltc.platform.observability import get_trace_id

        payload = inject_trace_id({"query_text": user_query, "scene_code": "S1"})
        await job_repo.enqueue(job_type="lead.search_pipeline.v1", payload=payload)

    The Worker ``runtime.py`` reads ``"_trace_id"`` from the payload and
    sets its formatter contextvar before executing the handler — every
    ``job.*`` / ``attempt.*`` log line automatically carries the origin
    trace-id.

    If no HTTP trace-id is set (e.g. cron or system-initiated jobs) the
    key is still present with an auto-generated UUID so the worker always
    has *some* correlation id.
    """
    from ltc.platform.observability import get_trace_id

    enriched = dict(payload)
    enriched.setdefault(TRACE_ID_PAYLOAD_KEY, get_trace_id())
    return enriched
