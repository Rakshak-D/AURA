from __future__ import annotations

import base64
import sys
from dataclasses import dataclass, field

import pytest

from backend.app.providers import ProviderConnectionContext
from backend.app.providers.errors import ProviderError, ProviderErrorCode
from backend.app.models.sql_models import ProviderConnection, ProviderCredential, User


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


class FakeCredentialManager:
    """In-memory test double; never reads or writes the user's Windows vault."""

    def __init__(self) -> None:
        self.entries: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.entries.get((service, username))

    def set_password(self, service: str, username: str, value: str) -> None:
        self.entries[(service, username)] = value


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
    monkeypatch.delenv("AURA_PROVIDER_MASTER_KEY", raising=False)
    monkeypatch.delenv("AURA_PROVIDER_MASTER_KEY_FILE", raising=False)

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


def _portable_key_text(byte_value: int = 7) -> str:
    return base64.b64encode(bytes([byte_value]) * 32).decode("ascii")


def _clear_portable_key_configuration(monkeypatch) -> None:
    monkeypatch.delenv("AURA_PROVIDER_MASTER_KEY", raising=False)
    monkeypatch.delenv("AURA_PROVIDER_MASTER_KEY_FILE", raising=False)


def test_portable_key_protector_accepts_valid_environment_key_and_restarts(monkeypatch, caplog):
    secret_store = _secret_store()
    encoded_key = _portable_key_text()
    monkeypatch.setenv("AURA_PROVIDER_MASTER_KEY", encoded_key)
    monkeypatch.delenv("AURA_PROVIDER_MASTER_KEY_FILE", raising=False)

    first_store = secret_store.SecretStore(secret_store.PortableKeyProtector())
    encrypted = first_store.encrypt_for_explicit_entry(7, "conn-a", "cred-a", "synthetic-key")
    second_store = secret_store.SecretStore(secret_store.PortableKeyProtector())

    assert len(encrypted.key_id) == 64
    assert second_store.decrypt(7, "conn-a", "cred-a", encrypted).value == "synthetic-key"
    assert encoded_key not in repr(secret_store.PortableKeyProtector())
    assert encoded_key not in repr(encrypted)
    assert encoded_key not in caplog.text


def test_portable_key_protector_accepts_file_key(monkeypatch, tmp_path):
    secret_store = _secret_store()
    _clear_portable_key_configuration(monkeypatch)
    secret_file = tmp_path / "provider-master-key"
    secret_file.write_text(_portable_key_text(8) + "\n", encoding="ascii")
    monkeypatch.setenv("AURA_PROVIDER_MASTER_KEY_FILE", str(secret_file))

    key = secret_store.PortableKeyProtector().active_key()

    assert key is not None
    assert len(key.key) == 32
    assert key.key == bytes([8]) * 32
    assert len(key.key_id) == 64


@pytest.mark.parametrize(
    "value",
    ["", "not-base64", base64.b64encode(b"short-key").decode("ascii")],
)
def test_portable_key_protector_rejects_invalid_environment_keys(monkeypatch, caplog, value):
    secret_store = _secret_store()
    _clear_portable_key_configuration(monkeypatch)
    monkeypatch.setenv("AURA_PROVIDER_MASTER_KEY", value)

    with pytest.raises(ProviderError) as error:
        secret_store.PortableKeyProtector().active_key()

    assert error.value.code is ProviderErrorCode.SECRET_STORE_UNAVAILABLE
    if value:
        assert value not in str(error.value)
        assert value not in caplog.text


@pytest.mark.parametrize(
    "configuration",
    ["missing", "both", "missing_file", "directory_file", "oversized_file"],
)
def test_portable_key_protector_fails_closed_for_missing_or_ambiguous_configuration(
    monkeypatch,
    tmp_path,
    configuration,
):
    secret_store = _secret_store()
    _clear_portable_key_configuration(monkeypatch)
    if configuration == "both":
        monkeypatch.setenv("AURA_PROVIDER_MASTER_KEY", _portable_key_text())
        monkeypatch.setenv("AURA_PROVIDER_MASTER_KEY_FILE", "unused")
    elif configuration == "missing_file":
        monkeypatch.setenv("AURA_PROVIDER_MASTER_KEY_FILE", str(tmp_path / "missing-secret"))
    elif configuration == "directory_file":
        monkeypatch.setenv("AURA_PROVIDER_MASTER_KEY_FILE", str(tmp_path))
    elif configuration == "oversized_file":
        oversized_file = tmp_path / "oversized-secret"
        oversized_file.write_bytes(b"x" * 129)
        monkeypatch.setenv("AURA_PROVIDER_MASTER_KEY_FILE", str(oversized_file))

    with pytest.raises(ProviderError) as error:
        secret_store.PortableKeyProtector().active_key()

    assert error.value.code is ProviderErrorCode.SECRET_STORE_UNAVAILABLE
    assert "missing-secret" not in str(error.value)
    if configuration == "missing":
        with pytest.raises(ProviderError) as create_error:
            secret_store.PortableKeyProtector().create_key()
        assert create_error.value.code is ProviderErrorCode.SECRET_STORE_UNAVAILABLE


def test_portable_key_protector_rejects_wrong_key_without_overwriting_record(
    monkeypatch,
    caplog,
):
    secret_store = _secret_store()
    _clear_portable_key_configuration(monkeypatch)
    monkeypatch.setenv("AURA_PROVIDER_MASTER_KEY", _portable_key_text(9))
    store = secret_store.SecretStore(secret_store.PortableKeyProtector())
    encrypted = store.encrypt_for_explicit_entry(9, "conn-a", "cred-a", "synthetic-secret")
    assert secret_store.PortableKeyProtector().load_key("bad-key-id") is None
    assert secret_store.PortableKeyProtector().load_key("é" * 64) is None

    monkeypatch.setenv("AURA_PROVIDER_MASTER_KEY", _portable_key_text(10))
    other_store = secret_store.SecretStore(secret_store.PortableKeyProtector())

    assert other_store.credential_state(encrypted) is secret_store.CredentialState.NEEDS_REENTRY
    with pytest.raises(ProviderError) as error:
        other_store.decrypt(9, "conn-a", "cred-a", encrypted)
    assert error.value.code is ProviderErrorCode.NEEDS_REENTRY
    assert "synthetic-secret" not in str(error.value)
    assert _portable_key_text(9) not in caplog.text
    assert "synthetic-secret" not in caplog.text
    assert encrypted.ciphertext


def test_production_factory_selects_portable_key_only_when_configured_on_linux(monkeypatch):
    secret_store = _secret_store()
    monkeypatch.setattr(secret_store.sys, "platform", "linux")
    _clear_portable_key_configuration(monkeypatch)

    assert isinstance(
        secret_store.build_production_secret_store()._protector,
        secret_store.UnsupportedKeyProtector,
    )
    monkeypatch.setenv("AURA_PROVIDER_MASTER_KEY", _portable_key_text(11))
    assert isinstance(
        secret_store.build_production_secret_store()._protector,
        secret_store.PortableKeyProtector,
    )


def test_production_factory_keeps_windows_credential_manager_default(monkeypatch):
    secret_store = _secret_store()
    monkeypatch.setattr(secret_store.sys, "platform", "win32")
    monkeypatch.setenv("AURA_PROVIDER_MASTER_KEY", _portable_key_text(12))

    store = secret_store.build_production_secret_store()

    assert isinstance(store._protector, secret_store.WindowsCredentialKeyProtector)


def test_windows_protector_uses_injected_credential_manager_double():
    secret_store = _secret_store()
    protector = secret_store.WindowsCredentialKeyProtector()
    fake_vault = FakeCredentialManager()
    protector._backend_instance = fake_vault

    assert protector.active_key() is None
    created = protector.create_key()

    assert protector.active_key() == created
    assert protector.load_key(created.key_id) == created.key
    assert fake_vault.get_password(
        secret_store._KEYRING_ACTIVE_SERVICE,
        secret_store._KEYRING_ACTIVE_USERNAME,
    ) == created.key_id
    encoded_key = fake_vault.get_password(
        secret_store._KEYRING_KEY_SERVICE_PREFIX + created.key_id,
        secret_store._KEYRING_KEY_USERNAME,
    )
    assert encoded_key is not None
    assert base64.urlsafe_b64decode(encoded_key.encode("ascii")) == created.key
    assert "key=<redacted>" in repr(created)


def test_portable_protector_never_uses_application_authentication_secrets(monkeypatch):
    secret_store = _secret_store()
    monkeypatch.setattr(secret_store.sys, "platform", "linux")
    _clear_portable_key_configuration(monkeypatch)
    monkeypatch.setenv("AUTH_SECRET_KEY", _portable_key_text(14))
    monkeypatch.setenv("SECRET_KEY", _portable_key_text(15))

    store = secret_store.build_production_secret_store()

    assert isinstance(store._protector, secret_store.UnsupportedKeyProtector)
    with pytest.raises(ProviderError) as error:
        store.encrypt_for_explicit_entry(14, "conn-a", "cred-a", "synthetic")
    assert error.value.code is ProviderErrorCode.SECRET_STORE_UNAVAILABLE


def test_portable_secret_store_round_trip_and_owner_scoped_deletion(
    isolated_runtime,
    monkeypatch,
):
    secret_store = _secret_store()
    encoded_key = _portable_key_text(13)
    raw_key = base64.b64decode(encoded_key)
    monkeypatch.setenv("AURA_PROVIDER_MASTER_KEY", encoded_key)
    monkeypatch.delenv("AURA_PROVIDER_MASTER_KEY_FILE", raising=False)
    store = secret_store.SecretStore(secret_store.PortableKeyProtector())
    session = isolated_runtime()
    try:
        user = User(name="Portable")
        session.add(user)
        session.flush()
        connection = ProviderConnection(
            id="portable-openai",
            user_id=user.id,
            name="Portable connection",
            provider_type="openai_compatible",
            base_url="https://api.example/v1",
        )
        session.add(connection)
        session.commit()

        store.save_credential(session, user.id, connection.id, "synthetic-provider-key")
        session.commit()
        record = ProviderCredential.get_owned(session, user.id, connection.id)
        assert record is not None
        assert raw_key not in record.ciphertext
        assert encoded_key not in repr(record)
        assert store.get_credential(session, user.id, connection.id).value == (
            "synthetic-provider-key"
        )
        assert store.delete_credential(session, user.id, connection.id) is True
        session.commit()
        assert ProviderCredential.get_owned(session, user.id, connection.id) is None
    finally:
        session.close()


def test_explicit_save_retrieve_and_delete_are_owner_scoped(isolated_runtime):
    secret_store = _secret_store()
    protector = FakeKeyProtector()
    store = secret_store.SecretStore(protector)
    session = isolated_runtime()
    try:
        alice = User(name="Alice")
        bob = User(name="Bob")
        session.add_all([alice, bob])
        session.flush()
        connection = ProviderConnection(
            id="alice-openai",
            user_id=alice.id,
            name="OpenAI",
            provider_type="openai_compatible",
            base_url="https://api.example/v1",
        )
        session.add(connection)
        session.commit()

        with pytest.raises(ProviderError) as error:
            store.save_credential(session, bob.id, connection.id, "wrong-owner-key")
        assert error.value.code is ProviderErrorCode.CONNECTION_REMOVED
        assert protector.created == 0

        store.save_credential(session, alice.id, connection.id, "synthetic-secret-one")
        session.commit()
        first = ProviderCredential.get_owned(session, alice.id, connection.id)
        assert first is not None
        first_credential_id = first.credential_id
        assert b"synthetic-secret-one" not in first.ciphertext
        assert "synthetic-secret-one" not in repr(first)
        assert store.get_credential(session, alice.id, connection.id).value == (
            "synthetic-secret-one"
        )
        with pytest.raises(ProviderError) as error:
            store.get_credential(session, bob.id, connection.id)
        assert error.value.code is ProviderErrorCode.CONNECTION_REMOVED

        store.save_credential(session, alice.id, connection.id, "synthetic-secret-two")
        session.commit()
        replaced = ProviderCredential.get_owned(session, alice.id, connection.id)
        assert replaced.credential_id == first_credential_id
        assert store.get_credential(session, alice.id, connection.id).value == (
            "synthetic-secret-two"
        )
        assert store.delete_credential(session, bob.id, connection.id) is False
        assert ProviderCredential.get_owned(session, alice.id, connection.id) is not None
        assert store.delete_credential(session, alice.id, connection.id) is True
        session.commit()
        assert ProviderCredential.get_owned(session, alice.id, connection.id) is None
        assert protector.active_key() is not None
    finally:
        session.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Credential Manager is Windows-only")
def test_windows_key_protector_uses_explicit_local_machine_persistence():
    secret_store = _secret_store()
    protector = secret_store.WindowsCredentialKeyProtector()
    backend = protector._get_backend()

    from keyring.backends.Windows import WinVaultKeyring
    from win32ctypes.pywin32 import win32cred

    assert isinstance(backend, WinVaultKeyring)
    assert backend.persist == win32cred.CRED_PERSIST_LOCAL_MACHINE
