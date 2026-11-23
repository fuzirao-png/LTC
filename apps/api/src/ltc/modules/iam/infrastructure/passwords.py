"""Password hashing adapter for IAM."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError


class Argon2PasswordVerifier:
    def __init__(self) -> None:
        self._hasher = PasswordHasher()

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (InvalidHashError, VerificationError):
            return False

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)
