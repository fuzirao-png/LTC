"""Worker process entry point.

Typical usage::

    python -m ltc_worker.main

The process:
1. Calls ``configure_worker_logging()``
2. Builds the ``ApplicationServices`` composition root (wires the real
   ``PostgreSQLJobRepository`` and UseCase implementations).
3. Enters the main loop: claim → handle → repeat.
4. On ``SIGTERM`` / ``SIGINT``: stops claiming, finishes the in-flight
   job (within a grace period), then exits.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

from .registry import build_current_phase_registry
from .runtime import WorkerRuntime

_logger = logging.getLogger("ltc.worker.main")


def configure_worker_logging() -> None:
    """Wire up structured JSON logging for the worker runtime."""
    level_name = os.getenv("LTC_LOG_LEVEL", "INFO")
    format_mode = os.getenv("LTC_LOG_FORMAT", "json")
    service_name = os.getenv("LTC_WORKER_NAME", "ltc-worker")

    log_level = getattr(logging, level_name.upper(), logging.INFO)
    handler = logging.StreamHandler()
    handler.setLevel(log_level)

    if format_mode == "console":
        from .observability._formatter import HumanFormatter
        handler.setFormatter(HumanFormatter(service_name=service_name))
    else:
        from .observability._formatter import JSONFormatter
        handler.setFormatter(JSONFormatter(service_name=service_name))
    handler.setStream(sys.stderr)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(log_level)
    root.addHandler(handler)

    for noisy in ("asyncio", "httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ── Composition root (stub — callers provide the real app) ──────────


def create_registry():
    """Factory for the handler registry."""
    return build_current_phase_registry()


def queue_names_from_environment() -> list[str]:
    """Return the queues this build is allowed to consume.

    CRM, Customer Analysis research, and meeting jobs are wired in
    ``WorkerApplication``. Other queues remain disabled until their concrete
    use cases are available.
    """
    raw = os.getenv("LTC_WORKER_QUEUE_NAMES", "crm,analysis,media")
    return list(dict.fromkeys(name.strip() for name in raw.split(",") if name.strip())) or ["crm"]


# ── Main loop ───────────────────────────────────────────────────────


class _ShutdownRequested(Exception):
    """Raised inside the main loop when a signal is received."""


async def run_worker_loop(
    app: object,
    *,
    worker_id: str | None = None,
    idle_sleep_seconds: float = 1.0,
    lease_seconds: int = 300,
    queue_names: list[str] | None = None,
) -> None:
    """Run the claim → handle loop until a shutdown signal arrives.

    *app* must implement the ``ApplicationServices`` protocol: it
    exposes a ``.jobs`` repository and one attribute per handler's
    ``use_case_attr``.

    The caller is responsible for constructing *app* (wiring the
    PostgreSQL connection pool, real UseCases, etc.).
    """
    if worker_id is None:
        import socket

        worker_id = f"{socket.gethostname()}-{os.getpid()}"

    if queue_names is None:
        queue_names = ["lead", "analysis", "mail", "media", "event", "data", "llm"]

    registry = build_current_phase_registry()
    shutdown_event = asyncio.Event()

    def _on_signal():
        _logger.info("worker.shutdown_signalled", extra={"worker_id": worker_id})
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except NotImplementedError:
            pass  # Windows / some event loops don't support add_signal_handler

    runtime = WorkerRuntime(worker_id=worker_id, registry=registry)

    _logger.info(
        "worker.started",
        extra={
            "worker_id": worker_id,
            "queue_names": queue_names,
            "registered_job_types": registry.job_types(),
        },
    )

    async def idle(seconds: float) -> None:
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def consume(queues: list[str], lease: int, *, schedule_crm: bool = False) -> None:
        while not shutdown_event.is_set():
            try:
                ensure_crm_jobs = getattr(app, "ensure_crm_jobs", None)
                if schedule_crm and ensure_crm_jobs is not None:
                    await asyncio.to_thread(ensure_crm_jobs)
                if await runtime.run_once(app, queues, lease):
                    continue
            except Exception:
                _logger.exception("worker.poll_failed", extra={"queue_names": queues})
            await idle(idle_sleep_seconds)

    async def recover_media() -> None:
        while not shutdown_event.is_set():
            try:
                await app.recover_media_jobs()
            except Exception:
                _logger.exception("worker.media_recovery_failed")
            await idle(5)

    try:
        if "media" not in queue_names or not hasattr(app, "recover_media_jobs"):
            await consume(queue_names, lease_seconds, schedule_crm="crm" in queue_names)
        else:
            from .media_job import MEDIA_LEASE_SECONDS

            other_queues = [queue for queue in queue_names if queue != "media"]
            loops = [consume(["media"], MEDIA_LEASE_SECONDS) for _ in range(app.media_job_concurrency)]
            if other_queues:
                loops.append(consume(other_queues, lease_seconds, schedule_crm="crm" in other_queues))
            await asyncio.gather(recover_media(), *loops)
    except _ShutdownRequested:
        pass
    finally:
        _logger.info("worker.stopped", extra={"worker_id": worker_id})


async def run_forever() -> None:
    from .runtime_app import create_application

    application = await create_application()
    try:
        await run_worker_loop(application, queue_names=queue_names_from_environment())
    finally:
        await application.close()


if __name__ == "__main__":
    configure_worker_logging()
    asyncio.run(run_forever())
