"""בדיקות יחידה לhardening של plaintext fallback ב-encryption.py.

ה-fix השורשי (06/2026): plaintext fallback מותר *רק* כש-`APP_ENV ==
"development"` במפורש. כל ערך אחר (כולל missing, typo, "staging",
"prod") → RuntimeError. בודקים את שלושת המסלולים:
- prod / staging / typo → raise.
- development + missing key → warning + None (fallback מותר).
- development + valid key → Fernet instance (round-trip עובד).

pure: אין DB, אין I/O — רק monkey-patch של get_settings.
"""

from cryptography.fernet import Fernet

import pytest

from app.utils import encryption


def _reset_module_state():
    """איפוס cache בין בדיקות — _get_fernet משתמש ב-globals."""
    encryption._FERNET = None
    encryption._FERNET_CHECKED = False


@pytest.fixture(autouse=True)
def reset_state():
    _reset_module_state()
    yield
    _reset_module_state()


def _patch_settings(monkeypatch, *, app_env: str, key: str | None):
    """monkey-patch ל-get_settings — קל יותר מליצור Settings אמיתי."""
    from app.config import Settings

    fake = Settings()
    # שדות אופציונליים — overrideים את מה שצריך לבדיקה.
    object.__setattr__(fake, "app_env", app_env)
    object.__setattr__(fake, "secrets_encryption_key", key)
    monkeypatch.setattr(encryption, "get_settings", lambda: fake)


def test_production_missing_key_raises(monkeypatch):
    """APP_ENV=production + key חסר → RuntimeError. ההגנה המקורית."""
    _patch_settings(monkeypatch, app_env="production", key=None)
    with pytest.raises(RuntimeError, match="SECRETS_ENCRYPTION_KEY"):
        encryption._get_fernet()


def test_staging_missing_key_raises(monkeypatch):
    """APP_ENV=staging + key חסר → RuntimeError. ההגנה החדשה (strict by
    default): רק development מקבל fallback."""
    _patch_settings(monkeypatch, app_env="staging", key=None)
    with pytest.raises(RuntimeError, match="Plaintext fallback is only allowed"):
        encryption._get_fernet()


def test_typo_prod_missing_key_raises(monkeypatch):
    """APP_ENV=prod (typo) + key חסר → RuntimeError. תופס drift נפוץ."""
    _patch_settings(monkeypatch, app_env="prod", key=None)
    with pytest.raises(RuntimeError, match="Plaintext fallback is only allowed"):
        encryption._get_fernet()


def test_empty_app_env_missing_key_raises(monkeypatch):
    """APP_ENV ריק (זה לא קורה ב-Settings אמיתי, אבל defense in depth)."""
    _patch_settings(monkeypatch, app_env="", key=None)
    with pytest.raises(RuntimeError, match="Plaintext fallback is only allowed"):
        encryption._get_fernet()


def test_development_missing_key_returns_none(monkeypatch, caplog):
    """APP_ENV=development + key חסר → None + warning. ה-opt-in היחיד."""
    _patch_settings(monkeypatch, app_env="development", key=None)
    with caplog.at_level("WARNING"):
        result = encryption._get_fernet()
    assert result is None
    assert any("plaintext" in r.message.lower() for r in caplog.records)


def test_development_valid_key_returns_fernet(monkeypatch):
    """APP_ENV=development + key תקין → Fernet instance עובד ל-round-trip."""
    key = Fernet.generate_key().decode()
    _patch_settings(monkeypatch, app_env="development", key=key)
    cipher = encryption._get_fernet()
    assert cipher is not None
    # round-trip
    encrypted = encryption.encrypt_secret("שלום")
    assert encrypted != "שלום"
    assert not encrypted.startswith("plain:")
    assert encryption.decrypt_secret(encrypted) == "שלום"


def test_production_valid_key_returns_fernet(monkeypatch):
    """APP_ENV=production + key תקין → Fernet. הזרימה התקינה בענן."""
    key = Fernet.generate_key().decode()
    _patch_settings(monkeypatch, app_env="production", key=key)
    cipher = encryption._get_fernet()
    assert cipher is not None


def test_production_invalid_key_raises(monkeypatch):
    """key קיים אבל לא בפורמט Fernet → RuntimeError בproduction."""
    _patch_settings(monkeypatch, app_env="production", key="not-a-valid-fernet-key")
    with pytest.raises(RuntimeError, match="Invalid SECRETS_ENCRYPTION_KEY"):
        encryption._get_fernet()


def test_assert_encryption_ready_raises_in_prod(monkeypatch):
    """`assert_encryption_ready` חושף את אותה השגיאה — משמש ל-eager validation
    ב-startup של main.py ו-jobs/_runner.py."""
    _patch_settings(monkeypatch, app_env="production", key=None)
    with pytest.raises(RuntimeError):
        encryption.assert_encryption_ready()


def test_assert_encryption_ready_passes_in_dev(monkeypatch):
    """ב-dev עם fallback — assert_encryption_ready עובר בלי לזרוק."""
    _patch_settings(monkeypatch, app_env="development", key=None)
    encryption.assert_encryption_ready()  # לא זורק


def test_decrypt_plain_prefix_works_without_key(monkeypatch):
    """tokens ישנים עם prefix `plain:` עדיין נקראים גם בדev בלי key —
    תאימות לאחור עם migration."""
    _patch_settings(monkeypatch, app_env="development", key=None)
    assert encryption.decrypt_secret("plain:secret-value") == "secret-value"
