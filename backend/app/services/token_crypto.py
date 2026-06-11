"""Authenticated encryption for server-side OAuth tokens."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.config import settings


TOKEN_PREFIX = "enc:v1:"


class TokenCryptoError(RuntimeError):
    """Base error for OAuth token encryption failures."""


class TokenEncryptionNotConfigured(TokenCryptoError):
    """Raised when no encryption key has been configured."""


class TokenEncryptionConfigurationError(TokenCryptoError):
    """Raised when a configured key is malformed."""


class TokenDecryptionError(TokenCryptoError):
    """Raised when encrypted token data cannot be authenticated or decrypted."""


def _configured_key_strings(raw_keys: str | None = None) -> list[str]:
    configured = (
        raw_keys
        if raw_keys is not None
        else getattr(settings, "GOOGLE_TOKEN_ENCRYPTION_KEYS", None)
    )
    return [
        item.strip()
        for item in str(configured or "").split(",")
        if item.strip()
    ]


def _build_multi_fernet(raw_keys: str | None = None) -> MultiFernet:
    key_strings = _configured_key_strings(raw_keys)
    if not key_strings:
        raise TokenEncryptionNotConfigured(
            "GOOGLE_TOKEN_ENCRYPTION_KEYS is not configured"
        )

    fernets: list[Fernet] = []
    for value in key_strings:
        try:
            fernets.append(Fernet(value.encode("ascii")))
        except (ValueError, TypeError, UnicodeEncodeError) as exc:
            raise TokenEncryptionConfigurationError(
                "GOOGLE_TOKEN_ENCRYPTION_KEYS contains an invalid Fernet key"
            ) from exc

    return MultiFernet(fernets)


def token_encryption_configured(raw_keys: str | None = None) -> bool:
    try:
        _build_multi_fernet(raw_keys)
    except TokenCryptoError:
        return False
    return True


def require_token_encryption_configured(
    raw_keys: str | None = None,
) -> None:
    _build_multi_fernet(raw_keys)


def is_encrypted_token(value: str | None) -> bool:
    return str(value or "").startswith(TOKEN_PREFIX)


def encrypt_token(
    value: str | None,
    *,
    raw_keys: str | None = None,
) -> str | None:
    token = str(value or "").strip()
    if not token:
        return None

    if is_encrypted_token(token):
        decrypt_token(token, raw_keys=raw_keys)
        return token

    encrypted = _build_multi_fernet(raw_keys).encrypt(
        token.encode("utf-8")
    )
    return TOKEN_PREFIX + encrypted.decode("ascii")


def decrypt_token(
    value: str | None,
    *,
    raw_keys: str | None = None,
) -> str | None:
    token = str(value or "").strip()
    if not token:
        return None

    if not is_encrypted_token(token):
        return token

    ciphertext = token[len(TOKEN_PREFIX):]

    try:
        plaintext = _build_multi_fernet(raw_keys).decrypt(
            ciphertext.encode("ascii")
        )
    except (
        InvalidToken,
        ValueError,
        TypeError,
        UnicodeEncodeError,
    ) as exc:
        raise TokenDecryptionError(
            "Stored OAuth token could not be decrypted"
        ) from exc

    try:
        return plaintext.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TokenDecryptionError(
            "Stored OAuth token is not valid UTF-8"
        ) from exc
