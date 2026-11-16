"""AES-GCM credential protection with an explicitly Windows-bound key store."""

from __future__ import annotations

import base64
import json
import os
import sys
import threading
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from .contracts import EphemeralCredential
from .errors import ProviderError, ProviderErrorCode

_KEYRING_ACTIVE_SERVICE = "Rakshak.AURA.ProviderMasterKey"
_KEYRING_ACTIVE_USERNAME = "active-key-id"
_KEYRING_KEY_SERVICE_PREFIX = "Rakshak.AURA.ProviderMasterKey."
_KEYRING_KEY_USERNAME = "aura-master-key"
_CREDENTIAL_FORMAT_VERSION = 1
_AES_KEY_BYTES = 32
_AES_GCM_NONCE_BYTES = 12


class CredentialState(StrEnum):
    AVAILABLE = "available"
    NEEDS_REENTRY = "needs_reentry"
    STORE_UNAVAILABLE = "store_unavailable"


@dataclass(frozen=True, slots=True)
class MasterKeyMaterial:
    key_id: str
    key: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not self.key_id:
            raise ValueError("master key id must be non-empty")
        if not isinstance(self.key, bytes) or len(self.key) != _AES_KEY_BYTES:
            raise ValueError("master key must contain exactly 256 bits")

    def __repr__(self) -> str:
        return f"MasterKeyMaterial(key_id={self.key_id!r}, key=<redacted>)"


@dataclass(frozen=True, slots=True)
class EncryptedCredential:
    version: int
    key_id: str
    credential_id: str
    nonce: bytes = field(repr=False)
    ciphertext: bytes = field(repr=False)

    def __repr__(self) -> str:
        return (
            "EncryptedCredential("
            f"version={self.version}, key_id={self.key_id!r}, "
            f"credential_id={self.credential_id!r}, nonce=<redacted>, ciphertext=<redacted>)"
        )


class KeyProtector(Protocol):
    def active_key(self) -> MasterKeyMaterial | None: ...

    def load_key(self, key_id: str) -> bytes | None: ...

    def create_key(self) -> MasterKeyMaterial: ...


class UnsupportedKeyProtector:
    """Fail-closed marker for production platforms without an approved key store."""

    @staticmethod
    def _unavailable() -> ProviderError:
        return ProviderError(ProviderErrorCode.SECRET_STORE_UNAVAILABLE)

    def active_key(self) -> MasterKeyMaterial | None:
        raise self._unavailable()

    def load_key(self, _key_id: str) -> bytes | None:
        raise self._unavailable()

    def create_key(self) -> MasterKeyMaterial:
        raise self._unavailable()


class WindowsCredentialKeyProtector:
    """Store only random master keys in the current user's Windows Credential Manager."""

    def __init__(self) -> None:
        self._backend_instance = None
        self._lock = threading.RLock()

    @staticmethod
    def _construct_backend():
        if sys.platform != "win32":
            raise ProviderError(ProviderErrorCode.SECRET_STORE_UNAVAILABLE)

        try:
            from keyring.backends.Windows import WinVaultKeyring

            backend = WinVaultKeyring()
            # The keyring backend defaults to enterprise persistence. AURA's
            # approved recovery scope is the same Windows user on this machine.
            backend.persist = "local machine"
            return backend
        except ProviderError:
            raise
        except Exception:
            raise ProviderError(ProviderErrorCode.SECRET_STORE_UNAVAILABLE) from None

    def _get_backend(self):
        if self._backend_instance is not None:
            return self._backend_instance
        with self._lock:
            if self._backend_instance is None:
                self._backend_instance = self._construct_backend()
        return self._backend_instance

    @staticmethod
    def _key_service(key_id: str) -> str:
        return f"{_KEYRING_KEY_SERVICE_PREFIX}{key_id}"

    def active_key(self) -> MasterKeyMaterial | None:
        try:
            backend = self._get_backend()
            key_id = backend.get_password(_KEYRING_ACTIVE_SERVICE, _KEYRING_ACTIVE_USERNAME)
            if not key_id:
                return None
            try:
                uuid.UUID(key_id)
            except (TypeError, ValueError):
                return None
            key = self.load_key(key_id)
            return MasterKeyMaterial(key_id, key) if key is not None else None
        except ProviderError:
            raise
        except Exception:
            raise ProviderError(ProviderErrorCode.SECRET_STORE_UNAVAILABLE) from None

    def load_key(self, key_id: str) -> bytes | None:
        try:
            normalized_id = str(uuid.UUID(key_id))
        except (TypeError, ValueError):
            return None

        try:
            encoded = self._get_backend().get_password(
                self._key_service(normalized_id),
                _KEYRING_KEY_USERNAME,
            )
            if encoded is None:
                return None
            key = base64.urlsafe_b64decode(encoded.encode("ascii"))
            if len(key) != _AES_KEY_BYTES:
                raise ProviderError(ProviderErrorCode.SECRET_STORE_UNAVAILABLE)
            return key
        except ProviderError:
            raise
        except Exception:
            raise ProviderError(ProviderErrorCode.SECRET_STORE_UNAVAILABLE) from None

    def create_key(self) -> MasterKeyMaterial:
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            key_id = str(uuid.uuid4())
            key = AESGCM.generate_key(bit_length=256)
            encoded = base64.urlsafe_b64encode(key).decode("ascii")
            backend = self._get_backend()
            key_service = self._key_service(key_id)

            # The target includes a fresh UUID and is checked before writing,
            # so a key is never silently overwritten.
            if backend.get_password(key_service, _KEYRING_KEY_USERNAME) is not None:
                raise ProviderError(ProviderErrorCode.SECRET_STORE_UNAVAILABLE)
            backend.set_password(key_service, _KEYRING_KEY_USERNAME, encoded)
            if backend.get_password(key_service, _KEYRING_KEY_USERNAME) != encoded:
                raise ProviderError(ProviderErrorCode.SECRET_STORE_UNAVAILABLE)

            backend.set_password(_KEYRING_ACTIVE_SERVICE, _KEYRING_ACTIVE_USERNAME, key_id)
            if backend.get_password(_KEYRING_ACTIVE_SERVICE, _KEYRING_ACTIVE_USERNAME) != key_id:
                raise ProviderError(ProviderErrorCode.SECRET_STORE_UNAVAILABLE)
            return MasterKeyMaterial(key_id, key)
        except ProviderError:
            raise
        except Exception:
            raise ProviderError(ProviderErrorCode.SECRET_STORE_UNAVAILABLE) from None


class SecretStore:
    """Encrypt/decrypt provider credentials without persisting plaintext."""

    def __init__(self, protector: KeyProtector) -> None:
        self._protector = protector
        self._lock = threading.RLock()

    def encrypt_for_explicit_entry(
        self,
        user_id: int,
        connection_id: str,
        credential_id: str,
        plaintext: str | EphemeralCredential,
    ) -> EncryptedCredential:
        self._validate_identity(user_id, connection_id, credential_id)
        value = plaintext.value if isinstance(plaintext, EphemeralCredential) else plaintext
        if not isinstance(value, str) or not value:
            raise ProviderError(ProviderErrorCode.INCOMPLETE_CONFIGURATION)

        try:
            with self._lock:
                master = self._protector.active_key()
                if master is None:
                    # This method represents an explicit credential entry or
                    # re-entry. Decryption and startup never create a key.
                    master = self._protector.create_key()
                self._validate_master_key(master.key)
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            nonce = os.urandom(_AES_GCM_NONCE_BYTES)
            aad = self._associated_data(
                user_id,
                connection_id,
                credential_id,
                master.key_id,
                _CREDENTIAL_FORMAT_VERSION,
            )
            ciphertext = AESGCM(master.key).encrypt(nonce, value.encode("utf-8"), aad)
            return EncryptedCredential(
                version=_CREDENTIAL_FORMAT_VERSION,
                key_id=master.key_id,
                credential_id=credential_id,
                nonce=nonce,
                ciphertext=ciphertext,
            )
        except ProviderError:
            raise
        except Exception:
            raise ProviderError(ProviderErrorCode.SECRET_STORE_UNAVAILABLE) from None

    def decrypt(
        self,
        user_id: int,
        connection_id: str,
        credential_id: str,
        encrypted: EncryptedCredential,
    ) -> EphemeralCredential:
        self._validate_identity(user_id, connection_id, credential_id)
        if not self._valid_encrypted_record(credential_id, encrypted):
            raise ProviderError(ProviderErrorCode.NEEDS_REENTRY)

        try:
            key = self._protector.load_key(encrypted.key_id)
        except ProviderError:
            raise
        except Exception:
            raise ProviderError(ProviderErrorCode.SECRET_STORE_UNAVAILABLE) from None
        if key is None:
            raise ProviderError(ProviderErrorCode.NEEDS_REENTRY)

        try:
            self._validate_master_key(key)
            from cryptography.exceptions import InvalidTag
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aad = self._associated_data(
                user_id,
                connection_id,
                credential_id,
                encrypted.key_id,
                encrypted.version,
            )
            plaintext = AESGCM(key).decrypt(encrypted.nonce, encrypted.ciphertext, aad)
            return EphemeralCredential(plaintext.decode("utf-8"))
        except ProviderError:
            raise
        except (InvalidTag, UnicodeDecodeError, ValueError):
            raise ProviderError(ProviderErrorCode.NEEDS_REENTRY) from None
        except Exception:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from None

    def credential_state(self, encrypted: EncryptedCredential) -> CredentialState:
        if not self._valid_encrypted_record(encrypted.credential_id, encrypted):
            return CredentialState.NEEDS_REENTRY
        try:
            key = self._protector.load_key(encrypted.key_id)
        except ProviderError as error:
            if error.code is ProviderErrorCode.SECRET_STORE_UNAVAILABLE:
                return CredentialState.STORE_UNAVAILABLE
            raise
        except Exception:
            return CredentialState.STORE_UNAVAILABLE
        if key is None:
            return CredentialState.NEEDS_REENTRY
        try:
            self._validate_master_key(key)
        except ProviderError:
            return CredentialState.STORE_UNAVAILABLE
        return CredentialState.AVAILABLE

    @staticmethod
    def _validate_identity(user_id: int, connection_id: str, credential_id: str) -> None:
        if not isinstance(user_id, int) or user_id <= 0:
            raise ProviderError(ProviderErrorCode.INCOMPLETE_CONFIGURATION)
        if not isinstance(connection_id, str) or not connection_id.strip():
            raise ProviderError(ProviderErrorCode.INCOMPLETE_CONFIGURATION)
        if not isinstance(credential_id, str) or not credential_id.strip():
            raise ProviderError(ProviderErrorCode.INCOMPLETE_CONFIGURATION)

    @staticmethod
    def _validate_master_key(key: bytes) -> None:
        if not isinstance(key, bytes) or len(key) != _AES_KEY_BYTES:
            raise ProviderError(ProviderErrorCode.SECRET_STORE_UNAVAILABLE)

    @staticmethod
    def _valid_encrypted_record(
        credential_id: str,
        encrypted: EncryptedCredential,
    ) -> bool:
        if not isinstance(encrypted, EncryptedCredential):
            return False
        return (
            encrypted.version == _CREDENTIAL_FORMAT_VERSION
            and encrypted.credential_id == credential_id
            and isinstance(encrypted.key_id, str)
            and bool(encrypted.key_id)
            and isinstance(encrypted.nonce, bytes)
            and len(encrypted.nonce) == _AES_GCM_NONCE_BYTES
            and isinstance(encrypted.ciphertext, bytes)
            and len(encrypted.ciphertext) >= 16
        )

    @staticmethod
    def _associated_data(
        user_id: int,
        connection_id: str,
        credential_id: str,
        key_id: str,
        version: int,
    ) -> bytes:
        identity = {
            "format": "aura-provider-credential",
            "version": version,
            "user_id": user_id,
            "connection_id": connection_id,
            "credential_id": credential_id,
            "key_id": key_id,
        }
        return json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_production_secret_store() -> SecretStore:
    """Select only the approved Windows protector; other platforms fail closed."""

    protector: KeyProtector
    if sys.platform == "win32":
        protector = WindowsCredentialKeyProtector()
    else:
        protector = UnsupportedKeyProtector()
    return SecretStore(protector)
