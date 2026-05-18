import pytest
from fastapi import HTTPException

from app.services.memory_pin import (
    hash_pin,
    validate_pin_format,
    verify_pin_hash,
)


def test_validate_pin_requires_exactly_6_digits():
    assert validate_pin_format("123456") == "123456"

    for value in ["12345", "1234567", "abc123", "12 456", "", None]:
        with pytest.raises(HTTPException):
            validate_pin_format(value)


def test_hash_pin_does_not_store_plaintext_and_verifies():
    stored = hash_pin("123456")

    assert "123456" not in stored
    assert stored.startswith("pbkdf2_sha256$")
    assert verify_pin_hash("123456", stored) is True
    assert verify_pin_hash("000000", stored) is False


def test_verify_rejects_invalid_hash():
    assert verify_pin_hash("123456", None) is False
    assert verify_pin_hash("123456", "bad-hash") is False
