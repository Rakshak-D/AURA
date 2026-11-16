# A1-A security checkpoint

## Task B credential protection

- Credential values are encrypted with AES-256-GCM, using a fresh 96-bit nonce for each explicit entry. The authenticated data binds the format/version, authenticated user ID, connection ID, credential ID, and key ID. Ciphertext includes the GCM authentication tag.
- The random 256-bit master key is stored in the current Windows user's Credential Manager through an explicitly constructed `WinVaultKeyring`. Persistence is explicitly set to `CRED_PERSIST_LOCAL_MACHINE`; the keyring library's automatic backend selection and enterprise roaming are not used.
- AURA does not write provider keys or master keys to files, environment variables, general user settings, logs, responses, prompts, or test evidence. The only production key store in A1 is Windows Credential Manager. There is no plaintext or fake-key production fallback.
- A missing master key for existing ciphertext reports `needs_reentry`; startup/decryption never creates a replacement. A new OS-protected key is created only during explicit credential entry/re-entry. Re-entry replaces only the explicitly edited connection's encrypted value.
- Credential operations fail closed if Windows key storage is unavailable. Linux and container key storage are unsupported in A1 and fail closed. Credentialless local-provider contexts can still be constructed and used.
- Local-machine Credential Manager recovery is limited to the same Windows user/profile on the same machine while the matching entry remains available. A database backup contains encrypted provider credential records but not the OS-protected master key. Restoring to another profile, machine, or after profile/key-store loss requires the owner to re-enter each affected provider key. AURA must retain old role references and report unavailable credentials without silently changing model assignments.

## Test evidence and limits

**PASS_SYNTHETIC** — The `FakeKeyProtector` exists only inside the test module. Tests cover authenticated identity binding, fresh nonce generation, ciphertext tampering, malformed records, missing-key/re-entry behavior, fail-closed storage errors, and absence of an environment-variable fallback. The Linux branch is exercised by platform simulation; it is not evidence from a Linux host/container.

**PASS_REAL** — On Windows with Python 3.11.7 and 3.12.10, the complete development dependency set installed successfully; the explicit `WinVaultKeyring` backend loaded and was configured for local-machine persistence. No credential was written to or read from the owner's actual Credential Manager.

**PASS_SYNTHETIC** — Targeted regression command on each Python version:

```powershell
& $PYTHON -m pytest tests/test_provider_secrets.py tests/test_authentication.py tests/test_foundation.py tests/test_ai_security.py tests/test_web_security.py tests/test_database_integrity.py -q
```

Result: 68 passed on Python 3.11.7 and 68 passed on Python 3.12.10. Each run emitted three existing Pydantic deprecation warnings from `backend/app/models/pydantic_models.py` and `backend/app/routes/routine.py`.

**NOT_TESTED** — Actual Windows Credential Manager credential write/read/recovery; native Linux/container execution; provider API integrations; network transport; schema migration (Task C); hosted CI. No live provider, real credential, or production database was used.

Task A import-laziness checks remain in `tests/test_provider_contracts.py`; the package import itself does not initialize a model, access the credential backend, or contact the network. Task C persistence and migration evidence will be recorded separately when that task is complete.
