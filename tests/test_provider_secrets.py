from __future__ import annotations

import sys
from dataclasses import dataclass, field

import pytest

from backend.app.providers import ProviderConnectionContext
from backend.app.providers.errors import ProviderError, ProviderErrorCode


def _secret_store():
    try:
        from backend.app.providers import secret_store
    except ImportError as exc:
        pytest.fail(f"secure credential storage is not available: {exc}")
    return secret_store


@dataclass(frozen=True)
class FakeMasterKey:
    key_id: str
    key: bytes = field(repr=False)


class FakeKeyProtector:
    """Test-only key protector. It is never selected by production settings."""

    def __init__(self) -> None:
        self.keys: dict[str, bytes] = {}
        self.active_id: str | None = None
        self.created = 0

    def active_key(self):
        if self.active_id is None:
            return None
        key = self.keys.get(self.active_id)
        return FakeMasterKey(self.active_id, key) if key is not None else None

    def load_key(self, key_id: str) -> bytes | None:
        return self.keys.get(key_id)

    def create_key(self):
        self.created += 1
        key_id = f"test-key-{self.created}"
        key = bytes([self.created]) * 32
        self.keys[key_id] = key
        self.active_id = key_id
        return FakeMasterKey(key_id, key)


class UnavailableKeyProtector:
    def active_key(self):
        raise ProviderError(ProviderErrorCode.SECRET_STORE_UNAVAILABLE)

    def load_key(self, _key_id: str):
        raise ProviderError(ProviderErrorCode.SECRET_STORE_UNAVAILABLE)

    def create_key(self):
        raise ProviderError(ProviderErrorCode.SECRET_STORE_UNAVAILABLE)


def test_ciphertext_round_trip_is_bound_to_user_connection_and_credential():
    secret_store = _secret_store()
    protector = FakeKeyProtector()
    store = secret_store.SecretStore(protector)
    api_key = "synthetic-test-key-do-not-use"

    encrypted = store.encrypt_for_explicit_entry(
        user_id=31,
        connection_id="conn-a",
        credential_id="credential-a",
        plaintext=api_key,
    )

    assert encrypted.version == 1
    assert encrypted.key_id == protector.active_id
    assert len(encrypted.nonce) == 12
    assert api_key.encode() not in encrypted.ciphertext
    assert api_key not in repr(encrypted)
    assert store.decrypt(31, "conn-a", "credential-a", encrypted).value == api_key
    assert repr(store.decrypt(31, "conn-a", "credential-a", encrypted)) == (
        "EphemeralCredential(<redacted>)"
    )

    for identity in (
        (32, "conn-a", "credential-a"),
        (31, "conn-b", "credential-a"),
        (31, "conn-a", "credential-b"),
    ):
        with pytest.raises(ProviderError) as error:
            store.decrypt(*identity, encrypted)
        assert error.value.code is ProviderErrorCode.NEEDS_REENTRY


def test_each_explicit_entry_uses_a_fresh_twelve_byte_nonce():
    secret_store = _secret_store()
    store = secret_store.SecretStore(FakeKeyProtector())

    first = store.encrypt_for_explicit_entry(1, "conn-a", "credential-a", "same-key")
    second = store.encrypt_for_explicit_entry(1, "conn-a", "credential-a", "same-key")

    assert len(first.nonce) == len(second.nonce) == 12
    assert first.nonce != second.nonce
    assert first.ciphertext != second.ciphertext


def test_modified_ciphertext_requires_credential_reentry():
    secret_store = _secret_store()
    store = secret_store.SecretStore(FakeKeyProtector())
    encrypted = store.encrypt_for_explicit_entry(1, "conn-a", "credential-a", "test-key")
    changed = secret_store.EncryptedCredential(
        version=encrypted.version,
        key_id=encrypted.key_id,
        credential_id=encrypted.credential_id,
        nonce=encrypted.nonce,
        ciphertext=encrypted.ciphertext[:-1] + bytes([encrypted.ciphertext[-1] ^ 1]),
    )

    with pytest.raises(ProviderError) as error:
        store.decrypt(1, "conn-a", "credential-a", changed)

    assert error.value.code is ProviderErrorCode.NEEDS_REENTRY


def test_malformed_ciphertext_record_fails_closed_as_reentry():
    secret_store = _secret_store()
    store = secret_store.SecretStore(FakeKeyProtector())
    malformed = secret_store.EncryptedCredential(
        version=1,
        key_id="test-key-1",
        credential_id="credential-a",
        nonce=None,
        ciphertext=None,
    )

    with pytest.raises(ProviderError) as error:
        store.decrypt(1, "conn-a", "credential-a", malformed)

    assert error.value.code is ProviderErrorCode.NEEDS_REENTRY


def test_missing_master_key_reports_reentry_without_generating_a_replacement():
    secret_store = _secret_store()
    protector = FakeKeyProtector()
    store = secret_store.SecretStore(protector)
    encrypted = store.encrypt_for_explicit_entry(1, "conn-a", "credential-a", "test-key")
    protector.keys.clear()
    previous_create_count = protector.created

    assert store.credential_state(encrypted) is secret_store.CredentialState.NEEDS_REENTRY
    with pytest.raises(ProviderError) as error:
        store.decrypt(1, "conn-a", "credential-a", encrypted)

    assert error.value.code is ProviderErrorCode.NEEDS_REENTRY
    assert protector.created == previous_create_count


def test_explicit_reentry_replaces_only_the_entered_connection_credential():
    secret_store = _secret_store()
    protector = FakeKeyProtector()
    store = secret_store.SecretStore(protector)
    old_connection = store.encrypt_for_explicit_entry(
        1, "conn-old", "credential-old", "old-key"
    )
    protector.keys.clear()
    previous_key_id = protector.active_id
    protector.active_id = None

    reentered = store.encrypt_for_explicit_entry(
        1, "conn-new", "credential-new", "new-key"
    )

    assert reentered.key_id != previous_key_id
    assert store.decrypt(1, "conn-new", "credential-new", reentered).value == "new-key"
    assert store.credential_state(old_connection) is secret_store.CredentialState.NEEDS_REENTRY
    with pytest.raises(ProviderError) as error:
        store.decrypt(1, "conn-old", "credential-old", old_connection)
    assert error.value.code is ProviderErrorCode.NEEDS_REENTRY


def test_unavailable_store_fails_closed_even_if_environment_contains_a_key(monkeypatch):
    secret_store = _secret_store()
    monkeypatch.setenv("AURA_PROVIDER_MASTER_KEY", "must-not-be-used-as-fallback")
    store = secret_store.SecretStore(UnavailableKeyProtector())

    with pytest.raises(ProviderError) as error:
        store.encrypt_for_explicit_entry(1, "conn-a", "credential-a", "new-key")

    assert error.value.code is ProviderErrorCode.SECRET_STORE_UNAVAILABLE
    assert "must-not-be-used-as-fallback" not in str(error.value)


def test_production_factory_fails_closed_on_linux_without_breaking_local_context(monkeypatch):
    secret_store = _secret_store()
    monkeypatch.setattr(secret_store.sys, "platform", "linux")

    store = secret_store.build_production_secret_store()
    local_context = ProviderConnectionContext(
        user_id=1,
        connection_id="local-ollama",
        provider_id="ollama",
        config_revision=0,
        local_only=True,
    )

    assert local_context.credential is None
    with pytest.raises(ProviderError) as error:
        store.encrypt_for_explicit_entry(1, "local-ollama", "credential-a", "unused")
    assert error.value.code is ProviderErrorCode.SECRET_STORE_UNAVAILABLE


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Credential Manager is Windows-only")
def test_windows_key_protector_uses_explicit_local_machine_persistence():
    secret_store = _secret_store()
    protector = secret_store.WindowsCredentialKeyProtector()
    backend = protector._get_backend()

    from keyring.backends.Windows import WinVaultKeyring
    from win32ctypes.pywin32 import win32cred

    assert isinstance(backend, WinVaultKeyring)
    assert backend.persist == win32cred.CRED_PERSIST_LOCAL_MACHINE
