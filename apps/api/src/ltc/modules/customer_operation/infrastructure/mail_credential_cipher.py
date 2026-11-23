from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class MailCredentialCipher:
    def __init__(self, key: str | None = None) -> None:
        raw_key = (key if key is not None else os.getenv("LTC_MAIL_CREDENTIAL_KEY", "")).strip()
        if key is None and not raw_key:
            raw_key = _read_local_env_key()
        if not raw_key:
            raise RuntimeError("LTC_MAIL_CREDENTIAL_KEY is not configured.")
        try:
            self._fernet = Fernet(raw_key.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise RuntimeError("LTC_MAIL_CREDENTIAL_KEY is invalid.") from exc

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeEncodeError) as exc:
            raise RuntimeError("Mailbox credential cannot be decrypted.") from exc


def _read_local_env_key() -> str:
    for directory in (Path.cwd(), *Path(__file__).resolve().parents):
        env_path = directory / ".env"
        if not env_path.is_file():
            continue
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith("LTC_MAIL_CREDENTIAL_KEY="):
                return line.split("=", 1)[1].strip()
    return ""
