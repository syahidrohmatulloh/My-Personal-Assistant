from cryptography.fernet import Fernet
import pytest

from app.services.token_crypto import (
    TOKEN_PREFIX,
    TokenDecryptionError,
    TokenEncryptionNotConfigured,
    decrypt_token,
    encrypt_token,
    is_encrypted_token,
    token_encryption_configured,
)


def _key() -> str:
    return Fernet.generate_key().decode("ascii")


def test_token_round_trip():
    key = _key()
    encrypted = encrypt_token("secret-token", raw_keys=key)

    assert encrypted is not None
    assert encrypted.startswith(TOKEN_PREFIX)
    assert encrypted != "secret-token"
    assert decrypt_token(encrypted, raw_keys=key) == "secret-token"


def test_legacy_plaintext_is_read_for_safe_migration():
    assert decrypt_token("legacy-token", raw_keys=_key()) == "legacy-token"
    assert not is_encrypted_token("legacy-token")


def test_missing_key_fails_closed_for_new_encryption():
    with pytest.raises(TokenEncryptionNotConfigured):
        encrypt_token("secret-token", raw_keys="")


def test_corrupted_ciphertext_is_rejected():
    with pytest.raises(TokenDecryptionError):
        decrypt_token(TOKEN_PREFIX + "not-valid", raw_keys=_key())


def test_multiple_keys_support_rotation():
    old_key = _key()
    new_key = _key()

    encrypted_with_old = encrypt_token(
        "rotating-token",
        raw_keys=old_key,
    )

    assert (
        decrypt_token(
            encrypted_with_old,
            raw_keys=f"{new_key},{old_key}",
        )
        == "rotating-token"
    )

    encrypted_with_new = encrypt_token(
        "new-token",
        raw_keys=f"{new_key},{old_key}",
    )

    assert decrypt_token(encrypted_with_new, raw_keys=new_key) == "new-token"


def test_encrypted_token_is_not_double_encrypted():
    key = _key()
    encrypted = encrypt_token("secret-token", raw_keys=key)

    assert encrypt_token(encrypted, raw_keys=key) == encrypted


def test_configuration_probe():
    assert token_encryption_configured(_key())
    assert not token_encryption_configured("")
