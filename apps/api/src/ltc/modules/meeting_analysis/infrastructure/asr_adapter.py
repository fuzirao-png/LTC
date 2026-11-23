"""OpenAI-compatible ASR (speech-to-text) adapter with retry logic.

Calls the /audio/transcriptions endpoint of an OpenAI-compatible API.
Supports both OpenAI-style endpoints and SiliconFlow (SenseVoiceSmall).
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from ltc.modules.meeting_analysis.domain.errors import AsrTranscriptionError
from ltc.modules.meeting_analysis.infrastructure.text_normalizer import to_simplified_text


_DEFAULT_MAX_RETRIES = 4
_DEFAULT_BASE_DELAY = 5.0
_DEFAULT_REQUEST_INTERVAL = 2.0
_DEFAULT_TIMEOUT = 600.0


class AsrAdapter:
    """Calls an OpenAI-compatible `/audio/transcriptions` endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = _DEFAULT_TIMEOUT,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        retry_base_delay_seconds: float = _DEFAULT_BASE_DELAY,
        request_interval_seconds: float = _DEFAULT_REQUEST_INTERVAL,
        proxy_url: str | None = None,
        request_gate: Callable[[Callable[[], httpx.Response]], httpx.Response] | None = None,
    ) -> None:
        self._model = model
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay_seconds
        self._request_interval = request_interval_seconds
        self._request_gate = request_gate
        self._is_siliconflow = "siliconflow" in base_url.lower()
        headers = {"Authorization": f"Bearer {api_key}"}
        transport = httpx.HTTPTransport(proxy=proxy_url) if proxy_url else None
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout_seconds,
            headers=headers,
            transport=transport,
        )

    @classmethod
    def from_settings(
        cls, settings: object, *,
        request_gate: Callable[[Callable[[], httpx.Response]], httpx.Response] | None = None,
    ) -> "AsrAdapter":
        """Create an AsrAdapter from application settings."""
        return cls(
            base_url=str(getattr(settings, "asr_base_url", "")),
            api_key=str(getattr(settings, "asr_api_key", "")),
            model=str(getattr(settings, "asr_model", "whisper-1")),
            timeout_seconds=float(getattr(settings, "asr_timeout_seconds", _DEFAULT_TIMEOUT)),
            max_retries=int(getattr(settings, "asr_max_retries", _DEFAULT_MAX_RETRIES)),
            retry_base_delay_seconds=float(getattr(settings, "asr_retry_base_delay_seconds", _DEFAULT_BASE_DELAY)),
            request_interval_seconds=float(getattr(settings, "asr_request_interval_seconds", _DEFAULT_REQUEST_INTERVAL)),
            proxy_url=getattr(settings, "asr_proxy_url", None) or None,
            request_gate=request_gate,
        )

    def transcribe(self, file_path: str) -> str:
        """Transcribe a single audio file. Returns the transcript text."""
        return self.transcribe_many([file_path])

    def transcribe_segment(self, file_path: str, transcript_ref: str) -> str:
        return self._transcribe_one(file_path, transcript_ref)

    def close(self) -> None:
        self._client.close()

    def transcribe_many(self, file_paths: list[str]) -> str:
        """Transcribe multiple audio files sequentially with rate limiting.

        Returns the concatenated transcript text separated by newlines.
        """
        parts: list[str] = []
        for file_path in file_paths:
            parts.append(self._transcribe_one(file_path))
            if len(file_paths) > 1:
                time.sleep(self._request_interval)
        return "\n".join(parts)

    def _transcribe_one(self, file_path: str, transcript_ref: str | None = None) -> str:
        path = Path(file_path)
        headers = {"Idempotency-Key": transcript_ref} if transcript_ref else None
        for attempt in range(self._max_retries + 1):
            try:
                with open(path, "rb") as f:
                    # SiliconFlow SenseVoiceSmall: multipart form with model as form field
                    # (NOT as data=, which some proxies reject)
                    if self._is_siliconflow:
                        files = {
                            "file": (path.name, f, self._guess_mime(path)),
                            "model": (None, self._model),
                        }
                        data = None
                    else:
                        files = {"file": (path.name, f, "audio/wav")}
                        data = {"model": self._model, "language": "zh", "response_format": "json"}

                    def send() -> httpx.Response:
                        return self._client.post("/audio/transcriptions", files=files, data=data, headers=headers)

                    resp = self._request_gate(send) if self._request_gate else send()
                if (resp.status_code == 429 or resp.status_code >= 500) and attempt < self._max_retries:
                    time.sleep(self._retry_delay(resp, attempt))
                    continue
                if resp.status_code >= 400:
                    # Wrap HTTP errors in AsrTranscriptionError with status detail
                    detail = resp.text[:500] if resp.text else f"HTTP {resp.status_code}"
                    raise AsrTranscriptionError(f"ASR API error {resp.status_code}: {detail}")
                resp.raise_for_status()
                payload = resp.json()
                text = payload.get("text") if isinstance(payload, dict) else None
                if not isinstance(text, str):
                    raise AsrTranscriptionError("ASR response missing 'text' field")
                return to_simplified_text(text)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                if attempt == self._max_retries:
                    raise AsrTranscriptionError(f"ASR request failed after {self._max_retries + 1} attempts") from exc
                delay = self._retry_delay(None, attempt)
                time.sleep(delay)
            except AsrTranscriptionError:
                raise
        raise AsrTranscriptionError(f"ASR transcription exhausted retries for {file_path}")

    def _retry_delay(self, response: httpx.Response | None, attempt: int) -> float:
        if response is not None and "Retry-After" in response.headers:
            try:
                return max(0.0, min(60.0, float(response.headers["Retry-After"])))
            except ValueError:
                pass
        return min(60.0, self._retry_base_delay * math.pow(2, attempt))

    @staticmethod
    def _guess_mime(path: Path) -> str:
        """Guess the MIME type for an audio file based on its extension."""
        ext = path.suffix.lower()
        mime_map = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".m4a": "audio/mp4",
            ".flac": "audio/flac",
            ".ogg": "audio/ogg",
            ".wma": "audio/x-ms-wma",
            ".aac": "audio/aac",
            ".webm": "audio/webm",
        }
        return mime_map.get(ext, "audio/wav")
