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

## A1-D secure provider transport

**PASS_SYNTHETIC** — The provider-independent `EndpointPolicy` validates the stored connection context and requested URL before any network backend is created. `ProviderTransport` uses HTTPCore's asynchronous connection pool with an injectable network-backend boundary. The focused tests use a fake DNS resolver and fake network backend; they open no real sockets and contact no provider.

**PASS_SYNTHETIC** — Explicit local loopback is limited to `127.0.0.1`, `[::1]`, and `localhost` resolving exclusively to those addresses. Local providers reject other destinations unless an exact `LocalNetworkGrant` matches user, connection, config revision, host, address, and port. A1-D does not wire that trusted grant contract to persistence or Settings, so grants default to none and LAN access remains fail-closed. Cloud-classified connections require HTTPS and every DNS answer must be public unicast; mixed results, private, loopback, link-local, metadata, reserved/special, unspecified, multicast, IPv4-mapped blocked addresses, and malformed answers are rejected. IPv4-mapped IPv6 addresses are normalized before policy checks.

**PASS_SYNTHETIC** — Server-owned Local only is checked before DNS for cloud providers and other nonlocal destinations, returning the existing `local_only_blocked` category without creating a pool or calling the connection boundary. Local loopback remains usable independently. The request URL must match the stored connection origin. URL parsing rejects embedded credentials, fragments, malformed/ambiguous authorities, unsupported schemes, control characters, and recognized credential-bearing query keys.

**PASS_SYNTHETIC** — Each operation resolves and validates all DNS answers, selects one validated numeric address, and connects using that numeric IP. The original hostname is carried separately for TLS SNI and certificate hostname verification; the HTTP/1.1 `Host` authority retains the configured hostname and nondefault port. TLS verification is required with TLS 1.2 minimum. A fresh pool is created and closed for every operation, with keep-alive disabled, HTTP/2 disabled, one connection per pool, and retries disabled. This forces DNS/policy revalidation for each operation and prevents pooled connections from crossing users or configuration revisions. Redirect responses are rejected without following their `Location`. Proxies are explicitly unset and HTTPX's TLS context is created with `trust_env=False`; proxy and certificate environment overrides do not affect the synthetic routing test.

**PASS_SYNTHETIC** — Defaults are 5 s connect, 30 s read, 10 s write, 5 s pool acquisition, 1 MiB ordinary response, 4 MiB cumulative streamed response, 120 s maximum stream duration, 10 concurrent operations, and 64 KiB response headers. Body sizes are counted incrementally. Requests send `Accept-Encoding: identity` and reject nonidentity response encodings, avoiding decompression-size bypass. Async context management, cancellation, timeout, oversize, and protocol-error paths close the response and pool and release the concurrency slot. Errors use normalized provider categories and safe fixed messages; request/response payloads are excluded from representations, and raw dependency exception text is not surfaced.

**PASS_SYNTHETIC** — On Windows, `& '<temp>\py311\Scripts\python.exe' -m pytest -q tests/test_provider_network_policy.py` and the corresponding `py312` command passed 93 tests each on Python 3.11.7 and 3.12.10. Both runs used the repository-pinned HTTPX 0.28.1 and HTTPCore 1.0.9 and emitted three existing Pydantic deprecation warnings. Test coverage includes local/cloud policy, Local only before network activity, fake peer IP and TLS/Host parameters, DNS rebinding, per-revision fresh connections, redirects, proxy environment isolation, response and stream limits, finite DNS timeout validation, public stream limit immutability, timeout normalization, cancellation cleanup, and secret redaction.

**PASS_SYNTHETIC** — On Windows, each Python version ran `python -m pytest -m 'not browser' --cov=backend.app --cov-report=term-missing --cov-report=xml:<versioned coverage path>` with `AURA_ENVIRONMENT=test`. Each collected 229 tests, passed 222, and deselected 7 browser tests; Python 3.11.7 emitted 3 warnings and Python 3.12.10 emitted 4 warnings, including the existing Python tar-extraction deprecation warning. The test doubles keep this evidence synthetic for network-security behavior; unrelated backend tests also use isolated test fixtures. Full-suite coverage was 84% for `endpoint_policy.py` and 83% for `transport.py` on both versions.

Commands executed in Windows PowerShell (the task-owned temporary venvs remain under the system temp directory because cleanup was rejected by command policy):

```powershell
& 'C:\Users\abhis\AppData\Local\Temp\aura-a1d-checks-1794898204120\py311\Scripts\python.exe' -m pytest -q tests/test_provider_network_policy.py
& 'C:\Users\abhis\AppData\Local\Temp\aura-a1d-checks-1794898204120\py312\Scripts\python.exe' -m pytest -q tests/test_provider_network_policy.py
```

Result: `93 passed, 3 warnings` on each Python version.

```powershell
$env:AURA_ENVIRONMENT = 'test'
$env:COVERAGE_FILE = 'C:\Users\abhis\AppData\Local\Temp\aura-a1d-checks-1794898204120\coverage311-final.dat'
& 'C:\Users\abhis\AppData\Local\Temp\aura-a1d-checks-1794898204120\py311\Scripts\python.exe' -m pytest -m 'not browser' --cov=backend.app --cov-report=term-missing --cov-report=xml:C:\Users\abhis\AppData\Local\Temp\aura-a1d-checks-1794898204120\coverage311-final.xml

$env:AURA_ENVIRONMENT = 'test'
$env:COVERAGE_FILE = 'C:\Users\abhis\AppData\Local\Temp\aura-a1d-checks-1794898204120\coverage312-final.dat'
& 'C:\Users\abhis\AppData\Local\Temp\aura-a1d-checks-1794898204120\py312\Scripts\python.exe' -m pytest -m 'not browser' --cov=backend.app --cov-report=term-missing --cov-report=xml:C:\Users\abhis\AppData\Local\Temp\aura-a1d-checks-1794898204120\coverage312-final.xml
```

Result: `222 passed, 7 deselected` on each version. The first emitted 3 warnings; the second emitted 4.

**PASS_REAL** — On Windows Python 3.11.7 and 3.12.10, `python -m compileall -q backend tests scripts`, `python -m ruff check backend tests scripts --select E4,E7,E9,F`, and `python -m pip check` passed. The resolved runtime versions were HTTPX 0.28.1 and HTTPCore 1.0.9. No dependency manifest changed. HTTPCore's public async network-backend interface and SNI extension were used; HTTP/2 is deliberately disabled. See the [HTTPX 0.28.1 dependency declaration](https://raw.githubusercontent.com/encode/httpx/0.28.1/pyproject.toml), [HTTPCore 1.0.9 changelog](https://raw.githubusercontent.com/encode/httpcore/1.0.9/CHANGELOG.md), [HTTPCore async connection source](https://raw.githubusercontent.com/encode/httpcore/1.0.9/httpcore/_async/connection.py), and [HTTPX 0.28.1 TLS configuration](https://raw.githubusercontent.com/encode/httpx/0.28.1/httpx/_config.py).

**NOT_TESTED** — No real socket, DNS resolver, TLS handshake, public service, local provider, LAN device, metadata service, or provider API was contacted. The fake backend demonstrates the destination and TLS parameters passed at the production transport boundary; it is not socket-level proof. Native Linux/Ubuntu execution, hosted CI, actual Windows Credential Manager operations, and HTTP/2 behavior were not tested. Trusted LAN grants have no production persistence source in this round and remain unavailable by default. No frontend, schema, migration, route, Chat, adapter, or dependency changes were made.

**Repository hygiene** — Added `backend/app/providers/endpoint_policy.py`, `backend/app/providers/transport.py`, and `tests/test_provider_network_policy.py`; appended this A1-D record to the existing review document. No directory or dependency was added. Temporary Python environments and coverage outputs were created under `C:\Users\abhis\AppData\Local\Temp\aura-a1d-checks-1794898204120`. After export, the command policy rejected the exact cleanup command for these task-owned artifacts; they remain preserved, and no alternate deletion mechanism was attempted. Existing ignored cache/evidence artifacts were inspected and preserved because their ownership predates or is uncertain for this round. The root `docs.zip` was not present when checked. No other file is staged or modified.

## A1-D differential security review

**Scope and risk** — Reviewed the two new production modules, the new test module, and this A1-D evidence addition against starting commit `fcb6d35dc905f406818c19f48ebe900080cd4755`. The endpoint parser, DNS policy, TLS setup, and outbound transport are HIGH risk because they guard external connections; the test and evidence files are LOW risk. The baseline had no provider transport implementation. No existing validation or security code was removed, and no dependency, schema, route, frontend, Chat, or adapter changed.

**Review result** — No unresolved HIGH or CRITICAL source finding was identified. During adversarial review, the DNS timeout accepted `NaN`/infinity and invalid per-call values, allowing a configured resolver timeout to be unbounded or behave unpredictably. Finite-positive validation was added for both the policy default and per-request override. The new regression cases first failed (7 failures, 3 passes), then passed (10 passed). A response-header size regression was added and passed. The public stream API also exposed internal flags that could disable duration enforcement or increase the byte limit; those overrides were removed from its signature, and two regression cases first failed then passed. The final focused transport suite passes 93 cases on both supported Python versions.

**Adversarial scenarios covered** — A cloud provider configured under Local only is rejected before resolver or connection calls; a public hostname that later resolves to metadata is rejected before a second connection; mixed public/private answers fail closed; an HTTP redirect is rejected without following its private `Location`; ambient proxy variables do not change the fake peer destination; and bounded response/stream handling closes resources on oversize, timeout, or cancellation. Synthetic sentinel credentials do not escape into safe errors or logs.

**Coverage and blast radius** — The full suite reports 84% line coverage for `endpoint_policy.py` and 83% for `transport.py` on both Python versions; 93 focused cases cover the policy and transport. Production call-site count is zero in this round because A1 provider adapters are intentionally excluded. The only use is the test module and the transport's own policy construction; connection enforcement therefore becomes active only when a later authorized adapter uses this boundary.

**Recommendation and limits** — A1-D is ready for supervising-engineer source review. Destination, SNI, certificate, authority, and cleanup assertions use HTTPCore's supported fake network-backend boundary; they are not real socket or TLS-handshake evidence. No real network was used, and native Linux/Ubuntu plus hosted CI remain NOT_TESTED. This round leaves LAN grants fail-closed because no trusted persisted authorization source exists yet.

**Method** — Read the baseline provider contracts/errors and connection context, inspected the implementation and tests, checked commit history for prior transport code, traced references with `rg`, reviewed HTTPX/HTTPCore versions and extension points, and exercised the denial and success paths with deterministic resolver/backend doubles. No A1-A behavior was modified.

## A1-D-R1 Local only queue preflight

**PASS_SYNTHETIC** — `ProviderStreamResponse.__aenter__` now invokes `EndpointPolicy.preflight_local_only` before acquiring a concurrency slot. The preflight and `resolve_and_pin` share `_preflight_connection`, so the Local only classification has one implementation. This preflight parses only the stored connection context and performs no DNS or network work. Full requested-endpoint resolution, DNS validation and numeric-IP pinning still complete before pool construction or connection.

**PASS_SYNTHETIC** — `test_local_only_denial_precedes_pool_wait_and_preserves_active_request` occupies the single slot with an in-flight authorized loopback stream, then attempts a cloud request while Local only is enabled. It verifies `local_only_blocked`, zero DNS calls for the rejected request, no additional fake network connection, and successful completion of the already active stream. The test first reproduced the defect as `TIMEOUT`; it passes after the correction.

**PASS_SYNTHETIC** — On Windows, `python -m pytest -q tests/test_provider_network_policy.py` passed 94 tests on Python 3.11.7 and 94 on Python 3.12.10, with 3 existing Pydantic warnings per run. `AURA_ENVIRONMENT=test python -m pytest -m 'not browser' -q` passed 223 tests and deselected 7 browser tests on each version; Python 3.11.7 emitted 3 existing warnings and Python 3.12.10 emitted 4, including the existing tar-extraction deprecation warning.

**PASS_REAL** — On Windows Python 3.11.7 and 3.12.10, `python -m compileall -q backend tests scripts`, `python -m ruff check backend tests scripts --select E4,E7,E9,F`, and `python -m pip check` passed. `git diff --check` passed. No dependency, schema, route, frontend, adapter, or A1-A change was introduced.

**NOT_TESTED** — Native Linux/Ubuntu, hosted CI and real network/socket behavior remain untested. All network assertions use the deterministic fake resolver and network backend.

## A1-E tool-contract and portable credential checkpoint

**PASS_SYNTHETIC** — The provider-independent stream contracts now expose text, tool-fragment, and completion event semantics. `ToolCallAssembler` reconstructs interleaved calls by stable index and ID, limits responses to 128 calls, bounds each name and argument payload plus the cumulative payload, rejects conflicting/missing identities and incomplete/non-object JSON, and redacts argument representations. No tool is resolved or executed. On Windows Python 3.11.7 and 3.12.10, `python -m pytest -q tests/test_provider_contracts.py tests/test_provider_secrets.py` passed 44 tests on each version.

**PASS_SYNTHETIC** — The portable protector was exercised with synthetic 32-byte keys through both direct environment configuration and a `_FILE` secret file. Tests cover strict key length/base64 checks, conflicting/missing/oversized/unreadable configuration, stable cross-instance AES-GCM decryption, wrong-key re-entry, no generated replacement, no application-secret fallback, Linux factory selection, unchanged Windows factory selection, encrypted database records, owner-scoped deletion, and key redaction. The Windows protector's key save/load path was exercised against an in-memory Credential Manager double. No real key or credential was used and no owner vault was accessed. No dependency or schema change was required.

**PASS_REAL** — On Windows Python 3.11.7 and 3.12.10, the complete non-browser suite `AURA_ENVIRONMENT=test python -m pytest -m 'not browser' -q` passed 246 tests and deselected 7 browser tests on each version. `python -m compileall -q backend tests scripts`, `python -m ruff check backend tests scripts --select E4,E7,E9,F`, `python -m pip check`, and `git diff --check` passed on both versions. Existing Pydantic deprecation warnings were reported; Python 3.12 also reported the existing tar-extraction deprecation warning.

**PASS_SYNTHETIC** — The unchanged A1-D transport/policy regression suite `python -m pytest -q tests/test_provider_network_policy.py` passed 94 tests on both Windows Python versions using deterministic resolver/network doubles; no real network or socket was used.

**NOT_TESTED** — Native Linux/Ubuntu or Docker execution: this host had no separate WSL Linux distribution and the Docker Desktop Linux daemon was unavailable. Actual Windows Credential Manager credential write/read/recovery was not performed; the Windows test only verifies explicit backend configuration. Hosted CI, provider requests, models, and real network access were not used. Portable key behavior therefore has synthetic configuration evidence on Windows, not native Linux/container evidence.

### A1-E differential review summary

**Baseline and scope** — Reviewed changes against `84eefef4d9b2ab8c95d2f915738cc85b438ddceb`. `git blame` attributes the prior Linux `UnsupportedKeyProtector` selection to accepted A1-A commit `1aec1ed`; this round retains that fail-closed class and changes selection only for Linux with an explicitly set provider-key variable. No accepted validation, encryption, AAD, owner checks, or A1-D policy code was removed. No schema or dependency file changed.

**Blast radius** — `build_production_secret_store()` has no application call sites in the current tree; its only call sites are tests. `ToolCallAssembler` and `ChatChunk.event_types` likewise have no runtime consumers yet, because adapters are outside this round. The new APIs therefore do not silently change existing Chat or credential flows.

**Adversarial review** — A model can submit arbitrarily many stream events, but assembly rejects excess indexes/calls, per-call overflow, cumulative payload overflow, ID conflicts, missing IDs, and malformed final JSON before returning any calls; it never dispatches names or parses arguments into actions. If a portable deployment loses or changes its configured key, the configured key ID cannot match the stored key ID, so decryption returns the existing safe re-entry state without altering ciphertext. Missing/invalid key configuration remains a safe store-unavailable failure. Environment-variable exposure and external key backup remain operator risks documented above.

**Review result** — No code finding identified in the reviewed A1-E diff. Confidence is limited to the tested Windows environment and deterministic test doubles; native Linux/container key configuration and real Credential Manager persistence remain unverified.
