# A1-A security checkpoint

## Task B credential protection

- Credential values are encrypted with AES-256-GCM, using a fresh 96-bit nonce for each explicit entry. The authenticated data binds the format/version, authenticated user ID, connection ID, credential ID, and key ID. Ciphertext includes the GCM authentication tag.
- The random 256-bit master key is stored in the current Windows user's Credential Manager through an explicitly constructed `WinVaultKeyring`. Persistence is explicitly set to `CRED_PERSIST_LOCAL_MACHINE`; the keyring library's automatic backend selection and enterprise roaming are not used.
- AURA does not write provider keys or master keys to files, environment variables, general user settings, logs, responses, prompts, or test evidence. The only production key store in A1 is Windows Credential Manager. There is no plaintext or fake-key production fallback.
- A missing master key for existing ciphertext reports `needs_reentry`; startup/decryption never creates a replacement. A new OS-protected key is created only during explicit credential entry/re-entry. Re-entry replaces only the explicitly edited connection's encrypted value.
- Explicit save/retrieve/delete operations are owner-scoped. Save and retrieve require an active owned connection; deletion removes only the encrypted database record. Connection removal uses the same scoped delete while preserving role records. Shared master keys are not deleted when one credential is removed.
- Credential operations fail closed if Windows key storage is unavailable. Linux and container key storage are unsupported in A1 and fail closed. Credentialless local-provider contexts can still be constructed and used.
- Local-machine Credential Manager recovery is limited to the same Windows user/profile on the same machine while the matching entry remains available. A database backup contains encrypted provider credential records but not the OS-protected master key. Restoring to another profile, machine, or after profile/key-store loss requires the owner to re-enter each affected provider key. AURA must retain old role references and report unavailable credentials without silently changing model assignments.

## Task B test evidence and limits (captured before Task C)

**PASS_SYNTHETIC** — The `FakeKeyProtector` exists only inside the test module. Tests cover authenticated identity binding, fresh nonce generation, ciphertext tampering, malformed records, missing-key/re-entry behavior, fail-closed storage errors, and absence of an environment-variable fallback. The Linux branch is exercised by platform simulation; it is not evidence from a Linux host/container.

**PASS_REAL** — On Windows with Python 3.11.7 and 3.12.10, the complete development dependency set installed successfully; the explicit `WinVaultKeyring` backend loaded and was configured for local-machine persistence. No credential was written to or read from the owner's actual Credential Manager.

**PASS_SYNTHETIC** — Targeted regression command on each Python version:

```powershell
& $PYTHON -m pytest tests/test_provider_secrets.py tests/test_authentication.py tests/test_foundation.py tests/test_ai_security.py tests/test_web_security.py tests/test_database_integrity.py -q
```

Result: 68 passed on Python 3.11.7 and 68 passed on Python 3.12.10. Each run emitted three existing Pydantic deprecation warnings from `backend/app/models/pydantic_models.py` and `backend/app/routes/routine.py`.

**NOT_TESTED** — Actual Windows Credential Manager credential write/read/recovery; native Linux/container execution; provider API integrations; network transport; schema migration (Task C); hosted CI. No live provider, real credential, or production database was used.

Task A import-laziness checks remain in `tests/test_provider_contracts.py`; the package import itself does not initialize a model, access the credential backend, or contact the network. Task C persistence and migration evidence will be recorded separately when that task is complete.

## Task C persistence evidence

**PASS_SYNTHETIC** — `tests/test_provider_storage.py` and `tests/test_database_integrity.py` use isolated temporary SQLite databases with foreign-key enforcement enabled. The v4 fixture contains users, tasks, reminders, documents, Chat history, and routine events. Migration to v5 preserves those records, leaves legacy `embedding_model_id` values null, creates no role selections, and enables Local only for existing users. A fresh version-0 schema also bootstraps to v5 with Local only enabled.

**PASS_SYNTHETIC** — Tests verify multiple same-type named connections per user; per-user name uniqueness; owner-scoped application lookups; database rejection of cross-user role and credential references; exact connection/model role bindings; encrypted credential save/retrieve/delete; credential deletion during connection soft removal; unchanged role references after config edits and soft removal; removed-target unavailability; and cache lookups scoped by owner, connection, revision, and model. Capability values are constrained to supported, unsupported, or unknown.

**PASS_SYNTHETIC** — Targeted command on Python 3.11.7 and Python 3.12.10:

```powershell
& $PYTHON -m pytest tests/test_provider_storage.py tests/test_database_integrity.py -q
```

Result: 21 passed on each version, with three existing Pydantic deprecation warnings per run.

**PASS_SYNTHETIC** — Full non-browser backend command on Python 3.11.7: `AURA_ENVIRONMENT=test python -m pytest -m "not browser" -q` → 123 passed, 7 browser tests deselected, 3 existing Pydantic deprecation warnings. Python 3.12.10: same command → 123 passed, 7 browser tests deselected, three Pydantic deprecation warnings and one existing Python tar extraction deprecation warning.

No real AURA database was opened or migrated. No provider API or model was contacted or loaded. Windows Credential Manager operations, Linux/container native execution, and hosted CI remain NOT_TESTED. No push was authorized.

## Post-review credential deletion correction

The final review identified that a connection tombstone initially left its encrypted credential row behind. The correction adds owner-scoped SecretStore save/retrieve/delete operations and makes connection tombstoning remove only that connection's encrypted row while leaving its role selection and shared OS master key intact. The Task B test module now contains 10 tests; final cross-version results are recorded here after the correction.

**PASS_SYNTHETIC** — `tests/test_provider_secrets.py` passed 10 tests on Python 3.11.7 and 3.12.10. The final combined command `python -m pytest tests/test_provider_secrets.py tests/test_provider_storage.py tests/test_database_integrity.py -q` passed 31 tests on each version, with three existing Pydantic warnings per run.

**PASS_SYNTHETIC** — Final full backend command `AURA_ENVIRONMENT=test python -m pytest -m "not browser" -q` passed 124 tests and deselected 7 browser tests on Python 3.11.7 (three existing Pydantic warnings) and Python 3.12.10 (three Pydantic warnings and one Python tar extraction warning). `ruff check backend tests scripts --select E4,E7,E9,F` and `pip check` passed.

## A1-A-R1 targeted correction evidence

**PASS_SYNTHETIC** — Provider-independent message contracts now carry tool declarations with bounded JSON input schemas, assistant calls with bounded provider IDs and redacted untrusted JSON arguments, and tool replies correlated by the original call ID. Stream chunks carry bounded partial call deltas and reject invalid indexes, identities, duplicate indexes, and oversized fragments. No action parsing, tool execution, registry, or agent loop was added.

**PASS_SYNTHETIC** — Schema v6 stores a constrained source label for context length and each tri-state capability: `controlled_probe`, `provider_metadata`, or `unknown`. Isolated tests cover a fresh schema, v4→v6 migration, and additive migration of a database with the previous A1-A v5 shape. The v5 migration preserves cached capability states, existing roles and preferences, defaults prior provenance to `unknown`, and rejects arbitrary diagnostic text. Cache ownership/connection/model/revision isolation remains covered.

**PASS_SYNTHETIC** — Focused command `python -m pytest tests/test_provider_contracts.py tests/test_provider_storage.py tests/test_provider_secrets.py tests/test_database_integrity.py -q` passed 44 tests on Python 3.11.7 and 44 on Python 3.12.10. Each run emitted three existing Pydantic deprecation warnings.

**PASS_SYNTHETIC** — Full non-browser command `AURA_ENVIRONMENT=test python -m pytest -m 'not browser' -q` passed 129 tests and deselected 7 browser tests on Python 3.11.7 (three existing Pydantic deprecation warnings) and Python 3.12.10 (the same three warnings plus one existing Python tar extraction deprecation warning). `ruff check backend tests scripts --select E4,E7,E9,F`, `git diff --check`, and `pip check` passed; no dependency manifest changed.

**NOT_TESTED** — Actual provider integrations/probes and actual Windows Credential Manager credential write/read/recovery. The Windows backend configuration test does not read or modify the owner's credentials. No real AURA database, credential, provider API, or model was used; A1-B remains unstarted.
