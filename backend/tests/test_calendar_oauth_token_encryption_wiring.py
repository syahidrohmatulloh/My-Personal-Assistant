from pathlib import Path


SOURCE = Path("app/routers/calendar_oauth.py").read_text(encoding="utf-8")


def test_google_tokens_are_encrypted_before_storage():
    assert "_encrypt_google_token(" in SOURCE
    assert '"access_token": encrypted_access_token' in SOURCE
    assert 'payload["refresh_token"] = refresh_token' in SOURCE


def test_google_tokens_are_decrypted_before_use():
    assert "decrypt_token(raw_access_token)" in SOURCE
    assert "decrypt_token(raw_refresh_token)" in SOURCE
    assert "_migrate_legacy_tokens(" in SOURCE


def test_google_error_response_body_is_not_logged():
    assert "response.text[:200]" not in SOURCE
