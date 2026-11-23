"""Application configuration for the LTC API skeleton."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import BaseModel, Field


class AppSettings(BaseModel):
    # App metadata
    app_name: str = Field(default="LTC API")
    app_version: str = Field(default="3.2")

    # Environment
    environment: str = Field(default="local")
    api_prefix: str = Field(default="/api/v1")
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000)

    # LLM (shared by customer_analysis, meeting_summary)
    llm_base_url: str = Field(default="")
    llm_api_key: str = Field(default="")
    llm_model: str = Field(default="")
    llm_proxy_url: str = Field(default="")

    # ASR (Speech-to-Text)
    asr_api_key: str = Field(default="")
    asr_base_url: str = Field(default="")
    asr_model: str = Field(default="whisper-1")
    asr_timeout_seconds: float = Field(default=600.0, gt=0)
    asr_max_retries: int = Field(default=4, ge=0)
    asr_retry_base_delay_seconds: float = Field(default=5.0, gt=0)
    asr_request_interval_seconds: float = Field(default=2.0, ge=0)
    asr_proxy_url: str = Field(default="")
    asr_max_parallel_requests: int = Field(default=4, ge=1, le=16)
    asr_target_latency_seconds: float = Field(default=2.0, gt=0, allow_inf_nan=False)
    audio_chunk_seconds: int = Field(default=60, ge=1)
    media_job_concurrency: int = Field(default=2, ge=1, le=16)

    # Database
    database_host: str = Field(default="127.0.0.1", min_length=1)
    database_port: int = Field(default=55432, ge=1, le=65535)
    database_name: str = Field(default="ltc", min_length=1)
    database_user: str = Field(default="ltc", min_length=1)
    database_password: str = Field(default="ltc_local_change_me", min_length=1)
    database_sslmode: str = Field(default="prefer", min_length=1)
    database_pool_min_size: int = Field(default=1, ge=1)
    database_pool_max_size: int = Field(default=10, ge=1)
    database_pool_timeout_seconds: float = Field(default=5.0, gt=0)
    redis_url: str = Field(default="")

    @property
    def database_dsn(self) -> str:
        return (
            f"postgresql://{quote(self.database_user, safe='')}:{quote(self.database_password, safe='')}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
            f"?sslmode={self.database_sslmode}"
        )

    # Backward-compat aliases for code still using old field names
    @property
    def db_host(self) -> str: return self.database_host
    @property
    def db_port(self) -> int: return self.database_port
    @property
    def db_name(self) -> str: return self.database_name
    @property
    def db_user(self) -> str: return self.database_user
    @property
    def db_password(self) -> str: return self.database_password
    @property
    def db_sslmode(self) -> str: return self.database_sslmode

    # IAM
    jwt_secret_key: str = Field(default="ltc-local-development-secret-change-me")
    jwt_access_token_ttl_minutes: int = Field(default=15)
    refresh_session_ttl_days: int = Field(default=7)

    # Outbound email (SMTP)
    smtp_host: str = Field(default="smtp.163.com")
    smtp_port: int = Field(default=465)
    smtp_username: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_use_ssl: bool = Field(default=True)
    mail_from: str = Field(default="")
    mail_api_key: str = Field(default="")
    mail_attachment_dir: str = Field(default=".local-data/email-attachments")
    mail_attachment_max_file_bytes: int = Field(default=20 * 1024 * 1024, ge=1)
    mail_attachment_max_message_bytes: int = Field(default=50 * 1024 * 1024, ge=1)

    # Inbound email (IMAP)
    inbound_mail_enabled: bool = Field(default=False)
    inbound_mail_host: str = Field(default="imap.163.com")
    inbound_mail_port: int = Field(default=993)
    inbound_mail_username: str = Field(default="")
    inbound_mail_password: str = Field(default="")
    inbound_mail_mailbox: str = Field(default="INBOX")
    inbound_mail_poll_seconds: int = Field(default=60)

    # Legacy
    meeting_analysis_api_base: str = Field(default="http://127.0.0.1:8000")
    legacy_demo_dir: str = Field(default="")

    # Optional read-only WeKnora knowledge search
    weknora_base_url: str = Field(default="")
    weknora_api_key: str = Field(default="")
    weknora_knowledge_base_ids: tuple[str, ...] = Field(default_factory=tuple)
    weknora_timeout_seconds: float = Field(default=20.0, gt=0, le=120)

    def resolve_legacy_demo_dir(self) -> Path | None:
        if self.legacy_demo_dir:
            return Path(self.legacy_demo_dir)
        return None


def _env_file_candidates(
    *,
    cwd: Path | None = None,
    module_file: Path | None = None,
) -> tuple[Path, ...]:
    current_directory = cwd or Path.cwd()
    source_file = (module_file or Path(__file__)).resolve()
    candidates = [current_directory / ".env"]

    for parent in source_file.parents:
        if (parent / "compose.yaml").is_file() and (parent / "apps" / "api").is_dir():
            candidates.append(parent / ".env")
            break

    return tuple(dict.fromkeys(candidates))


def _env(name: str, default: str = "") -> str:
    raw_value = os.getenv(name)
    if raw_value is not None:
        return raw_value
    for env_path in _env_file_candidates():
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip().lower() == name.lower():
                return value.strip().strip('"').strip("'")
    return default


def _read_int(name: str, default: int) -> int:
    raw_value = _env(name)
    if raw_value is None:
        return default
    if raw_value == "":
        return default
    return int(raw_value)


def _read_bool(name: str, default: bool) -> bool:
    raw_value = _env(name)
    if raw_value == "":
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings(
        redis_url=_env("LTC_REDIS_URL"),
        app_name=_env("LTC_APP_NAME", "LTC API"),
        app_version=_env("LTC_APP_VERSION", "3.2"),
        environment=_env("LTC_ENV", "local"),
        api_prefix=_env("LTC_API_PREFIX", "/api/v1"),
        host=_env("LTC_API_HOST", "127.0.0.1"),
        port=_read_int("LTC_API_PORT", 8000),
        # LLM
        llm_base_url=_env("LTC_LLM_BASE_URL", _env("OPENAI_BASE_URL", _env("LLM_BASE_URL", ""))),
        llm_api_key=_env("LTC_LLM_API_KEY", _env("OPENAI_API_KEY", _env("LLM_API_KEY", ""))),
        llm_model=_env("LTC_LLM_MODEL", _env("OPENAI_MODEL", _env("LLM_MODEL", "gpt-5.6-terra"))),
        llm_proxy_url=_env("LTC_LLM_PROXY_URL", _env("LLM_PROXY_URL", "")),
        # ASR
        asr_api_key=_env("LTC_ASR_API_KEY", _env("ASR_API_KEY", "")),
        asr_base_url=_env("LTC_ASR_BASE_URL", _env("ASR_BASE_URL", "")),
        asr_model=_env("LTC_ASR_MODEL", _env("ASR_MODEL", "whisper-1")),
        asr_timeout_seconds=float(_env("LTC_ASR_TIMEOUT_SECONDS", "600")),
        asr_max_retries=_read_int("LTC_ASR_MAX_RETRIES", 4),
        asr_retry_base_delay_seconds=float(_env("LTC_ASR_RETRY_BASE_DELAY_SECONDS", "5")),
        asr_request_interval_seconds=float(_env("LTC_ASR_REQUEST_INTERVAL_SECONDS", "2")),
        asr_proxy_url=_env("LTC_ASR_PROXY_URL", ""),
        asr_max_parallel_requests=_read_int("LTC_ASR_MAX_PARALLEL_REQUESTS", 4),
        asr_target_latency_seconds=float(_env("LTC_ASR_TARGET_LATENCY_SECONDS", "2.0")),
        audio_chunk_seconds=_read_int("LTC_AUDIO_CHUNK_SECONDS", 60),
        media_job_concurrency=_read_int("LTC_MEDIA_JOB_CONCURRENCY", 2),
        # Database
        database_host=_env("LTC_DB_HOST", "127.0.0.1"),
        database_port=_read_int("LTC_DB_PORT", 55432),
        database_name=_env("LTC_DB_NAME", "ltc"),
        database_user=_env("LTC_DB_USER", "ltc"),
        database_password=_env("LTC_DB_PASSWORD", "ltc_local_change_me"),
        database_sslmode=_env("LTC_DB_SSLMODE", "prefer"),
        database_pool_min_size=_read_int("LTC_DB_POOL_MIN_SIZE", 1),
        database_pool_max_size=_read_int("LTC_DB_POOL_MAX_SIZE", 10),
        database_pool_timeout_seconds=float(_env("LTC_DB_POOL_TIMEOUT_SECONDS", "5")),
        # IAM
        jwt_secret_key=_env("LTC_JWT_SECRET_KEY", "ltc-local-development-secret-change-me"),
        jwt_access_token_ttl_minutes=_read_int("LTC_JWT_ACCESS_TOKEN_TTL_MINUTES", 15),
        refresh_session_ttl_days=_read_int("LTC_REFRESH_SESSION_TTL_DAYS", 7),
        # SMTP
        smtp_host=_env("SMTP_HOST", "smtp.163.com"),
        smtp_port=_read_int("SMTP_PORT", 465),
        smtp_username=_env("SMTP_USERNAME", ""),
        smtp_password=_env("SMTP_PASSWORD", ""),
        smtp_use_ssl=_read_bool("SMTP_USE_SSL", True),
        mail_from=_env("MAIL_FROM", ""),
        mail_api_key=_env("MAIL_API_KEY", ""),
        mail_attachment_dir=_env("LTC_MAIL_ATTACHMENT_DIR", ".local-data/email-attachments"),
        mail_attachment_max_file_bytes=_read_int("LTC_MAIL_ATTACHMENT_MAX_FILE_BYTES", 20 * 1024 * 1024),
        mail_attachment_max_message_bytes=_read_int("LTC_MAIL_ATTACHMENT_MAX_MESSAGE_BYTES", 50 * 1024 * 1024),
        # Inbound mail
        inbound_mail_enabled=_read_bool("INBOUND_MAIL_ENABLED", False),
        inbound_mail_host=_env("INBOUND_MAIL_HOST", "imap.163.com"),
        inbound_mail_port=_read_int("INBOUND_MAIL_PORT", 993),
        inbound_mail_username=_env("INBOUND_MAIL_USERNAME", ""),
        inbound_mail_password=_env("INBOUND_MAIL_PASSWORD", ""),
        inbound_mail_mailbox=_env("INBOUND_MAIL_MAILBOX", "INBOX"),
        inbound_mail_poll_seconds=_read_int("INBOUND_MAIL_POLL_SECONDS", 60),
        # Legacy
        meeting_analysis_api_base=_env("MEETING_ANALYSIS_API_BASE", "http://127.0.0.1:8000"),
        legacy_demo_dir=_env("LEGACY_DEMO_DIR", ""),
        # WeKnora
        weknora_base_url=_env("LTC_WEKNORA_BASE_URL", "").rstrip("/"),
        weknora_api_key=_env("LTC_WEKNORA_API_KEY", ""),
        weknora_knowledge_base_ids=tuple(value.strip() for value in _env("LTC_WEKNORA_KNOWLEDGE_BASE_IDS", "").split(",") if value.strip()),
        weknora_timeout_seconds=float(_env("LTC_WEKNORA_TIMEOUT_SECONDS", "20")),
    )
