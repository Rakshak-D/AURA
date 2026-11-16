# AURA A1 — Model-Agnostic Provider Layer Implementation Plan

> **For agentic workers:** Use the subagent-driven-development or executing-plans skill when implementation is authorized. Implement one task at a time, test before implementation, and use checkbox tracking.

**Goal:** Implement the approved A1 provider architecture while preserving A0 authentication, action, privacy, startup, and CI guarantees.

**Architecture:** A small backend/app/providers package owns typed contracts, provider adapters, secret handling, endpoint policy, and one pinned outbound transport. User-owned records select exact connection/model pairs for Router, Chat, and Embedding. Existing application services call a provider service with structured messages. A1-D produces a static Settings proof and stops for owner approval before A1-E UI work.

**Tech stack:** Existing FastAPI, SQLAlchemy, SQLite, Pydantic, vanilla JavaScript, and Playwright; direct async HTTPX transport; cryptography AES-GCM; explicit Windows Credential Manager backend. No model framework, model download, GPU, or new frontend framework.

**Spec:** docs/superpowers/specs/2026-11-16-a1-model-agnostic-design.md

## Global constraints

- This plan is A1 only. Do not add A2–A7 behavior, deploy, push, merge, or alter branch history.
- Keep all permanent project files inside the repository. Do not create another checkout or project copy.
- Preserve A0 authentication, /api/chat response fields, nine strict action types, ownership checks, destructive-action confirmation, browser network guard, startup laziness, and every security test.
- Add no tool-execution loop, silent model selection, silent role reassignment, silent model download, telemetry, live cloud test dependency, or plaintext credential fallback.
- Every provider operation must use the shared endpoint policy and transport, including discovery, health, capabilities, chat, streaming, and embeddings.
- Local only defaults to enabled. Permit explicitly validated loopback in either mode. For remote-enabled requests, require HTTPS and a globally routable unicast target; reject special-use, private, metadata, mixed, or ambiguous destinations.
- Remote requests contain only the current user message and the minimal system instruction. Do not send chat history, tasks, profile, RAG results, or local documents to remote providers.
- Use deterministic fake transports in CI. Tests must not require real provider credentials or cloud connectivity.
- Run regression tests before implementation for each task; demonstrate the expected failure, implement the smallest change, rerun the focused test, then run the relevant broader suite. Commit each independently verified implementation task. This plan itself does not authorize implementation.
- At every checkpoint run git diff --check, inspect staged/unstaged/untracked and relevant ignored artifacts, and report hygiene using Checkpoint hygiene below. Never use wildcard or broad recursive deletion.
- Do not modify historical A0 evidence. Preserve uncertain files, including the pre-existing root docs.zip and ignored A0 browser log identified during planning.

## Review focus

| Review risk | Required control | Named tests that must cover it |
|---|---|---|
| SSRF through DNS changes, address ambiguity, redirects, or proxies | Validate all DNS answers at connection time, reject mixed answers, pin the exact numeric peer, disable redirects and ambient proxies | test_dns_rebinding_is_revalidated_and_pinned, test_mixed_dns_answers_fail_before_connect, test_ipv4_mapped_addresses_use_normalized_policy, test_redirect_is_not_followed, test_metadata_targets_never_connect, test_transport_ignores_ambient_proxy in tests/test_provider_network_policy.py |
| Credential theft, false recovery, or plaintext fallback | AES-256-GCM with identity-bound AAD; explicit OS-backed Windows store; fail closed when unavailable; Linux/container production credential operations unsupported | test_ciphertext_is_authenticated_and_bound_to_owner, test_missing_master_key_requires_reentry, test_unavailable_store_fails_closed, test_linux_secret_operations_fail_closed, test_credentials_never_appear_in_settings_export_logs_or_errors in tests/test_provider_secrets.py and tests/test_provider_settings_api.py |
| Cross-user connection access or silent role reassignment | Composite ownership checks; role stores connection ID and model ID; edit/delete retain the original role reference | test_connection_id_is_scoped_to_authenticated_user, test_multiple_named_connections_are_independent, test_edit_or_remove_never_reassigns_role, test_removed_role_returns_unavailable_error in storage, API, and service tests |
| Local personal context reaching a cloud provider or model output changing actions | Remote payload minimization; existing strict action parsing and authenticated ownership remain authoritative | test_remote_chat_contains_only_current_message, test_provider_output_cannot_execute_actions, and the existing tests/test_ai_security.py suite |
| Startup regressions, guessed capabilities, or model-specific tokens returning | No startup load/probe; tri-state capabilities; backend source scan; full existing suite and CI matrix | test_provider_import_and_startup_are_lazy, test_missing_metadata_is_unknown, test_no_model_specific_tokens_in_backend, tests/test_foundation.py, and tests/test_ai_security.py |

## Repository inventory

The initial implementation should reuse the existing flat tests/, backend, frontend, workflow, and evidence locations.

### New files expected

One justified source package:

- backend/app/providers/__init__.py
- backend/app/providers/contracts.py
- backend/app/providers/errors.py
- backend/app/providers/registry.py
- backend/app/providers/service.py
- backend/app/providers/endpoint_policy.py
- backend/app/providers/transport.py
- backend/app/providers/secret_store.py
- backend/app/providers/ollama.py
- backend/app/providers/openai_compatible.py
- backend/app/providers/legacy_gguf.py
- backend/app/providers/anthropic.py
- backend/app/providers/gemini.py
- backend/app/providers/sentence_transformers.py

New focused tests in the existing test directory:

- tests/test_provider_contracts.py
- tests/test_provider_secrets.py
- tests/test_provider_storage.py
- tests/test_provider_network_policy.py
- tests/test_provider_adapters.py
- tests/test_provider_settings_api.py
- tests/test_provider_service_migration.py
- tests/test_provider_source_tokens.py

One authenticated route module:

- backend/app/routes/model_settings.py

Final evidence files, written in the already existing docs/evidence/a1-model-providers/ directory as their stage completes:

- ARCHITECTURE.md
- PROVIDER_MATRIX.md
- CAPABILITY_PROBES.md
- DEPENDENCY_CHANGES.md
- SECURITY_REVIEW.md
- TEST_RESULTS.md
- RESOURCE_MEASUREMENTS.md
- REAL_MODEL_RUNS.md
- SOURCE_CHANGES.md
- A1_REPORT.md

Only at A1-D, create the approved proof directory and its static source/screenshots:

- docs/proofs/a1-model-settings/index.html
- docs/proofs/a1-model-settings/models.css
- Three final responsive screenshots at 1440×900, 1024×768, and 390×844, plus one readable eight-state contact sheet showing all proof states. The failed-connection and unavailable-role states in the contact sheet must show mobile presentation.

Do not add a separate test folder, plan folder, adapter-specific directories, placeholder files, or duplicate evidence folders. No A1-E UI files are authorized until the A1-D proof receives approval.

### Existing files expected to change

- Dependencies: requirements.txt, requirements-dev.txt only if test-only tooling is required.
- Persistence and app wiring: backend/app/models/sql_models.py, backend/app/models/pydantic_models.py, backend/app/database.py, backend/app/main.py, backend/app/runtime_diagnostics.py, backend/app/routes/__init__.py.
- Existing services: backend/app/services/chat_service.py, intent_service.py, routine_service.py, rag_service.py.
- Existing backend tests/fixtures: tests/conftest.py, tests/test_ai_security.py, tests/test_authentication.py, tests/test_database_integrity.py, tests/test_foundation.py, and any directly affected existing API tests.
- CI: .github/workflows/ci.yml.
- Only after proof approval: frontend/index.html, frontend/js/settings.js, frontend/css/styles.css, and directly affected tests/frontend_contracts.test.mjs, tests/test_frontend_contracts.py, tests/browser/test_frontend_smoke.py.
- Delete backend/app/models/llm_models.py only after every caller, fixture, test, and diagnostic has migrated and the new local adapters preserve the explicitly selected local paths.

## Contracts to implement

Define these in backend/app/providers/contracts.py before provider code:

- ProviderId: ollama, openai_compatible, legacy_gguf, anthropic, gemini, and the explicitly local sentence_transformers embedding adapter.
- ModelRole: router, chat, embedding.
- CapabilityState: supported, unsupported, unknown.
- Immutable structured values: ProviderMessage(role, content, tool_call_id=None), ProviderModel(id, display_name, metadata), CapabilityValue(state, evidence=None), ModelCapabilities(provider_id, model_id, context_length, tools, json, vision, streaming, embeddings, checked_at, source), HealthResult, ChatRequest, ChatResult, and ChatChunk.
- ProviderAdapter async protocol: list_models(context) -> Sequence[ProviderModel]; health_check(context) -> HealthResult; get_capabilities(context, model_id) -> ModelCapabilities; chat(context, request) -> ChatResult; stream_chat(context, request) -> AsyncIterator[ChatChunk]; embed(context, model_id, text) -> Sequence[float].
- Normalize provider failures in errors.py to safe categories: incomplete configuration, unavailable, authentication failed, model unavailable, unsupported capability, timeout/cancelled, Local only blocked, endpoint destination blocked, connection removed, secure store unavailable/re-entry needed, rate limited, and invalid response. Do not include raw credentials, response bodies, or credential-bearing URLs in user-visible messages or logs.
- ModelService resolves by (user_id, role) and an exact saved (connection_id, model_id). Define chat(db: Session, user_id: int, role: ModelRole, messages: Sequence[ProviderMessage], options: ChatOptions) -> ChatResult; stream_chat with the same inputs -> AsyncIterator[ChatChunk]; and embed(db: Session, user_id: int, text: str) -> Sequence[float]. No caller can select a connection by unscoped ID.
- Role fallback is limited to the approved rules: unset Router can use the configured Chat selection; unset Embedding can use Chat only if embedding support is verified. Unknown capability never qualifies. No other automatic assignment or substitution.
- ProviderTransport is the only network boundary. Define request(method, url, headers, body, policy_context) and stream(request, policy_context) operations returning normalized response/async chunks. Adapters receive this transport/context and must not create a socket or HTTP client directly.
- EndpointPolicy.resolve_and_pin(url, local_only) returns a validated pinned destination carrying original hostname, numeric peer IP, port, scheme, and TLS server name. The transport must connect to that peer without a second DNS lookup while preserving the configured hostname for Host and TLS validation.
- SecretStore supports explicit save, retrieve/use, delete, and re-entry state operations keyed by authenticated user and connection. It receives a KeyProtector dependency; only the Windows production implementation may access the native vault, while tests inject a fake.

## Staged implementation

Each task below is a gated checkpoint. Do not skip its test-first sequence or hygiene report. “Commit” means a local, scoped commit after that task passes; no push is authorized.

### A1-A — Baseline, contracts, dependencies, and persistence

#### Task 1 — Task A: Reconfirm baseline and define provider contracts

**Files:** add tests/test_provider_contracts.py, then backend/app/providers/__init__.py, contracts.py, errors.py, and registry.py.

**Test-first steps:**

1. Add tests for structured message role validation, capability tri-state defaults, provider error normalization, registry coverage for all five required provider adapters plus the local Sentence Transformers embedding adapter, and unknown metadata remaining unknown.
2. Run python -m pytest tests/test_provider_contracts.py -q and confirm the contract tests fail before the package exists.
3. Implement only types, safe errors, and registry construction. Do not add network or model loading.
4. Rerun the focused module, then python -m pytest tests/test_foundation.py tests/test_ai_security.py -q.

**Gate:** Importing provider contracts has no network, secret-store, model, GPU, filesystem model scan, or heavy optional-runtime side effect.

**Evidence:** Start ARCHITECTURE.md with the dependency graph, contract version, role resolution rules, and explicit no-assignment migration decision.

**Hygiene:** Only the four provider package files and the contract test are new. Confirm no package cache, generated fixture, or downloaded model entered the repository.

#### Task 2 — Task B: Minimal dependencies and secret protection

**Files:** add tests/test_provider_secrets.py; add backend/app/providers/secret_store.py; update requirements.txt and, only if needed, requirements-dev.txt.

**Dependency decision to verify and record:** the versions verified during planning are HTTPX 0.28.1, cryptography 50.0.2, keyring 25.7.0, and Windows-only pywin32-ctypes 0.2.3. Recheck official release/install metadata before pinning; if any pin changes, record the reason, platform marker, license, wheel and installed-size delta in DEPENDENCY_CHANGES.md. Explicitly instantiate the Windows Credential Manager backend; do not use keyring auto-selection. Set local-machine persistence rather than enterprise roaming. Do not install the full pywin32 package if pywin32-ctypes satisfies the explicit backend.

**Test-first steps:**

1. Inject a test-only KeyProtector fake; tests must verify 256-bit AES-GCM keys, fresh 96-bit nonces, authenticated user/credential identity AAD, ciphertext tamper rejection, key rotation/re-entry states, and no cleartext persistence.
2. Test that missing/unavailable Windows vault and all production Linux/container credential operations fail closed. Test that local credentialless providers can still be used.
3. Test that an absent master-key record with existing ciphertext never silently creates a replacement key or overwrites ciphertext at startup.
4. Run python -m pytest tests/test_provider_secrets.py -q, add the implementation, and rerun.

**Gate:** Only Windows Credential Manager is a production key backend in A1. Linux CI fakes are injectable only in tests and cannot be enabled through production configuration. Secret values remain transient in memory and do not enter database settings, logs, responses, prompts, exports, or exception text.

**Evidence:** Document exact dependency versions and installation-size delta in DEPENDENCY_CHANGES.md; document supported Windows account/profile recovery, unsupported Linux/container behavior, backup/restore limitations, and per-connection re-entry in SECURITY_REVIEW.md.

**Hygiene:** No test key, local credential, environment file, or temporary vault dump remains. Keep dependency lock or cache output out of Git unless an existing repository convention requires it.

#### Task 3 — Task C: Schema v5 and user-owned provider records

**Files:** add tests/test_provider_storage.py; update backend/app/models/sql_models.py, backend/app/models/pydantic_models.py, and backend/app/database.py.

**Data model:**

- ProviderConnection: owner, stable ID, unique per-user name, provider type, base URL/configuration, config revision, soft-delete timestamp.
- ProviderCredential: owner and connection identity, format/key version, nonce, ciphertext including the authenticated tag; no plaintext or master key.
- ModelRoleSelection: owner, role, exact connection ID and model ID. A composite owner/connection foreign key prevents cross-user assignments.
- ProviderCapabilityCache: owner, connection, config revision, model, safe capability values, and check timestamp.
- UserModelPreference: Local only preference, with a migration-safe true default for existing users.
- Add nullable Document.embedding_model_id or the narrowest equivalent compatible with the current vector schema. Legacy rows remain unidentified and require re-index before querying with a selected model.

**Test-first steps:**

1. Build a v4 SQLite fixture containing all current user/task/document data. Assert migration to v5 preserves existing data and creates no role selection.
2. Assert missing preference resolves Local only to true; connection names are unique only within one user; composite ownership prevents assigning or reading another user's connection.
3. Assert editing and soft-deleting a connection never changes or deletes role selections; a deleted role target is surfaced as unavailable.
4. Assert cache isolation by user, connection, revision, and model; config edits invalidate only the affected connection's cache.
5. Run python -m pytest tests/test_provider_storage.py tests/test_database_integrity.py -q, implement migration, and rerun.

**Gate:** Bump REQUIRED_SCHEMA_VERSION from 4 to 5 only with a tested, additive migration. Check SQLite foreign-key enforcement and preserve existing schema migration behavior. Do not populate Chat, Router, or Embedding assignments automatically from old GGUF paths or manifests.

**Evidence:** Add storage/migration behavior and legacy-vector re-index semantics to ARCHITECTURE.md and SECURITY_REVIEW.md.

**Hygiene:** Use isolated temporary database fixtures owned by tests; verify they are not committed and that no real AURA database was touched.

### A1-B.1 — Shared network boundary and provider adapters

#### Task D — SSRF endpoint policy and pinned transport

**Files:** add tests/test_provider_network_policy.py; add backend/app/providers/endpoint_policy.py and transport.py.

**Required boundary:** The policy accepts an explicit loopback IP or localhost resolving entirely to loopback in either mode. Local only rejects all non-loopback destinations. With Local only off, non-loopback requires HTTPS and globally routable unicast. Reject private, shared, link-local, loopback-as-remote, reserved, documentation, multicast, unspecified, translation/special-purpose ranges, and all listed metadata targets. Reject userinfo, ambiguous authorities, unsafe schemes, invalid ports, and mixed policy resolutions. Normalize IPv4-mapped IPv6 before classification. Resolve immediately before each connection and connect to a validated numeric peer while retaining the configured hostname for Host and TLS SNI. Revalidate every operation. Redirects and ambient proxy inheritance are disabled.

**Test-first steps in tests/test_provider_network_policy.py:**

1. Add the named Review Focus tests and coverage for both policy modes, valid public HTTPS, literal loopback, localhost, loopback that resolves to non-loopback, empty DNS, mixed public/private answers, and exact peer pinning.
2. Cover IPv4-mapped loopback/private/metadata, IPv4 and IPv6 metadata endpoints (169.254.169.254, 169.254.170.2, 100.100.100.200, fd00:ec2::254, fd20:ce::254, metadata.google.internal), every provider operation, redirects from loopback and public HTTPS, and no proxy use.
3. Use a fake resolver and recording socket/transport; for every rejected destination assert zero connection attempts. Exercise DNS rebinding between configuration and connect and between successive requests.
4. Add actual HTTPX transport tests, beyond fake-policy tests: the connected numeric peer equals the validated IP; no second hostname resolution occurs; TLS SNI and certificate hostname verification use the original hostname; HTTP Host and authority are correct; redirects and ambient proxies cannot bypass policy; and pooled connection reuse still triggers destination revalidation. Use official HTTPX/HTTPCore extension points where supported. If a custom transport is necessary, document its exact dependencies, pinned versions, and security consequences.
5. Run python -m pytest tests/test_provider_network_policy.py -q, implement the policy/transport, then run the entire module and service contract tests.

**Gate:** No adapter can bypass policy by passing a URL, supplying its own client, using redirects, or using proxy environment variables. Policy errors are safe and do not disclose internal resolution details beyond a useful blocked-destination category.

**Evidence:** Add an endpoint/range matrix and test coverage results to SECURITY_REVIEW.md.

**Hygiene:** No packet captures, resolver dumps, or ad hoc local servers remain. Retain only deterministic tests and final evidence.

#### Task E — Ollama local adapter

**Files:** add tests/test_provider_adapters.py; add backend/app/providers/ollama.py.

**Test-first steps:** Controlled transport tests for installed model listing (/api/tags), chat and streaming (/api/chat), embeddings (/api/embed), error normalization, cancellation/timeouts, unknown capabilities, and routing every request through shared endpoint policy. Verify no pull, server start, model download, or local model auto-selection.

**Gate:** Ollama loopback remains usable with Local only enabled and no credential. No real daemon is started in CI.

**Evidence:** Add synthetic adapter cases and unverified capabilities to PROVIDER_MATRIX.md and CAPABILITY_PROBES.md.

**Hygiene:** No model data or daemon logs are created.

#### Task F — Multiple OpenAI-compatible connections

**Files:** update tests/test_provider_adapters.py; add backend/app/providers/openai_compatible.py.

**Test-first steps:** Use two connection contexts with independent base URLs, credentials, model IDs, config revisions, and capability caches. Test /v1/models, chat completions, streaming/SSE, and embeddings; provider errors and malformed/incomplete discovery; explicit manual model ID when listing is unavailable; safe unknown capability state; cancellation and timeouts; policy enforcement for all operations.

**Gate:** Never key adapter state/cache by provider type alone. Model role and selection always identify both connection ID and model ID. No capability claims inferred from model names.

**Evidence:** Include at least two separate synthetic named connections and their independent role/model assignments in PROVIDER_MATRIX.md.

**Hygiene:** Fixtures contain fake endpoints and tokens only.

#### Task G — Existing GGUF and Sentence Transformers local adapters

**Files:** add backend/app/providers/legacy_gguf.py and sentence_transformers.py; update backend/app/config.py only if an explicit existing path must be surfaced without changing defaults; update adapter tests.

**Test-first steps:** Mock optional runtimes to verify imports remain lazy; test a local GGUF chat-template/tokenizer-template path for structured messages and safe incompatibility; test configured on-disk-only loading; test Sentence Transformers Embedding-only behavior and vector shape/model identity; test no network or model download; test serialized legacy model switch/release where runtime supports it.

**Gate:** Existing model paths remain candidates only and are not automatically assigned to a role. Runtime loads only after explicit role use. A missing path or unrepresentable message returns a safe unavailable error.

**Evidence:** Record compatibility limits and measured release behavior in PROVIDER_MATRIX.md and RESOURCE_MEASUREMENTS.md.

**Hygiene:** Do not inspect model directories beyond explicitly configured paths. Do not copy, download, or commit weights.

#### Task H — Anthropic and Gemini native adapters

**Files:** update tests/test_provider_adapters.py; add backend/app/providers/anthropic.py and gemini.py.

**Test-first steps:** Controlled fixtures for Anthropic Messages, model listing when supported, streaming events, safe error responses, and token handling; Gemini native request, model listing, streaming, and supported embedding call. Test provider-native serialization, cancellation, timeout, malformed responses, and shared transport enforcement. Keep server-side state disabled where the current API allows it.

**Gate:** Do not emulate either provider with OpenAI wire format. Confirm exact endpoint/auth/stream details against current official provider docs at implementation and cite those references in adapter docstrings or evidence. Gemini implementation must use the current recommended Interactions API if it meets the approved one-turn, no-tool-execution design; document any compatibility exception before coding it. No provider tool call is executed by AURA.

**Evidence:** Record native API version, synthetic status, and each unverified capability in PROVIDER_MATRIX.md.

**Hygiene:** No live credentials, requests, or provider responses are retained.

### A1-B.2 — Authenticated model Settings and provider service

#### Task I — Role resolution and safe authenticated APIs

**Files:** add tests/test_provider_settings_api.py; add backend/app/routes/model_settings.py; update backend/app/main.py and backend/app/routes/__init__.py; add/complete backend/app/providers/service.py.

**API surface:** Keep APIs under authenticated /api/settings/models routes. Minimum operations:

- GET /api/settings/models and GET /api/settings/models/provider-types.
- POST /api/settings/models/connections; PATCH and DELETE /api/settings/models/connections/{connection_id}.
- Write-only credential PUT and explicit DELETE for /api/settings/models/connections/{connection_id}/credential.
- GET /api/settings/models/connections/{connection_id}/models.
- POST /api/settings/models/connections/{connection_id}/test.
- GET /api/settings/models/connections/{connection_id}/models/{model_id}/capabilities.
- PUT /api/settings/models/roles/{role} storing exact connection/model; explicit DELETE to clear.
- PUT /api/settings/models/local-only.

**Test-first steps:** Require authenticated user for each route; test strict request schemas, cross-user IDs, two OpenAI-compatible connections, independent credentials/model list/cache, same connection edit, soft delete, role references retained, unavailable roles, Router/Embedding approved fallback conditions, explicit user clear/reassign, Local only toggle, API export/settings exclusion, and keys never returned, logged, or included in validation errors. Verify every probe passes the policy service.

**Gate:** Never merge provider fields into generic User.settings; no route accepts ownership from request body. Reads expose only non-secret has_api_key/safe state. Connection edit never changes roles; delete tombstones and removes its credential while role record remains.

**Evidence:** Record endpoints and synthetic ownership/security cases in ARCHITECTURE.md and SECURITY_REVIEW.md.

**Hygiene:** Use existing route conventions. No generic abstraction layer, extra API namespace package, or generated OpenAPI snapshot.

### A1-C — Migrate existing inference and RAG paths

#### Task J — Migrate Chat, intent, routine, and RAG

**Files:** add/update tests/test_provider_service_migration.py; update backend/app/services/chat_service.py, intent_service.py, routine_service.py, rag_service.py, and backend/app/routes/chat.py only if passing authenticated user context requires it.

**Test-first steps:**

1. Add failing tests for Chat structured messages and unchanged response contract (response, action_taken, data, suggestions), no-model fallback, intent classification per authenticated user, audit of routine parsing, and Embedding-role document indexing/query.
2. Assert remote Chat receives only the active user message plus minimal system instruction, with no prior turns, tasks, profile, local documents, or RAG content.
3. Assert same-provider local calls may use only data already permitted by the current authenticated service path. Enforce embedding model identity and dimension; legacy unidentified vectors require re-index and cannot be searched as if compatible.
4. Assert provider output remains a proposal. Existing strict nine-action parsing, authenticated user identity, ownership lookups, and destructive confirmations still decide actions; provider-native tool calls are ignored/rejected as data.
5. Run focused migration and existing AI security tests before implementation; migrate call sites to ModelService; rerun focused tests.

**Gate:** No raw model-specific prompt control tokens, stop-token lists, or token cleanup remain in backend application code. detect_intent and all inference/embedding operations receive current authenticated user identity. Routine parsing is migrated or documented as dead code with tests proving it has no remaining caller.

**Evidence:** Add data-boundary cases, action invariants, and existing-vector re-index behavior to SECURITY_REVIEW.md and TEST_RESULTS.md.

**Hygiene:** Remove backend/app/models/llm_models.py only after rg proves there are no production/test imports and all required local adapters preserve configured paths. Do not remove unrelated optional-runtime dependencies until measured and confirmed unused.

#### Task K — Startup diagnostics, fixtures, and source-token guard

**Files:** add tests/test_provider_source_tokens.py; update backend/app/runtime_diagnostics.py, backend/app/main.py, tests/conftest.py, tests/test_foundation.py, tests/test_authentication.py, tests/test_database_integrity.py, tests/test_ai_security.py; update .github/workflows/ci.yml only for the source scan and any required install changes.

**Test-first steps:** Test runtime diagnostics do not load models, call key store, perform discovery, or send network requests. Test safe readiness output distinguishes unconfigured/selected/unavailable without secret or URL leakage. Add a scanner across every backend application source file for the design-prohibited model-control and end-token strings; do not evade with encoding, concatenation, or generated strings.

**Gate:** All prior auth, ownership, action-confirmation, Local only, CORS, external browser request guard, startup-lazy, and injection/security tests remain present and pass. Diagnostics are configuration-only.

**Evidence:** Record a complete security-test inventory and source scan in TEST_RESULTS.md and SECURITY_REVIEW.md.

**Hygiene:** Ensure test fixtures reset only their own test DB/provider state; do not introduce cross-test singleton state. Remove only exact test-created temporary DBs/traces after verifying their paths.

### A1-B/C — CI and staged backend acceptance

#### Task L — Preserve and extend CI; collect backend evidence

**Files:** update .github/workflows/ci.yml, relevant requirements, and evidence files in the existing A1 evidence directory.

**Test-first steps:** Update only relevant job inputs. Preserve six existing checks: Linux Python 3.11, Linux Python 3.12, Windows Python 3.12, frontend syntax/security, Playwright browser regressions, and container smoke. Add provider tests and source scan to existing jobs rather than replacing coverage or relaxing gates. Keep live providers, keys, models, and GPU out of CI.

**Local verification commands at this checkpoint:**

- Linux/Python 3.11 and Linux/Python 3.12: python -m pytest --collect-only -q; AURA_ENVIRONMENT=test python -m pytest -m "not browser" --cov=backend.app --cov-report=term-missing --cov-report=xml; python -m compileall -q backend tests scripts; python -m ruff check backend tests scripts --select E4,E7,E9,F; python -m pip check.
- Windows/Python 3.12: python -m pytest --collect-only -q; AURA_ENVIRONMENT=test python -m pytest -m "not browser" -q; python -m pip check. This job validates imports and compatibility but never requires a real Windows credential write.
- Frontend: preserve current Node syntax, contract, dangerous sink, and WebSocket token URL checks.
- Browser: install existing browser requirements, run python -m playwright install --with-deps chromium, then AURA_RUN_BROWSER=1 AURA_BROWSER_EVIDENCE_DIR=tests/browser-artifacts python -m pytest -m browser -q.
- Container: preserve production image, readiness, restart, and backup/restore smoke tests; verify Linux credential operations fail closed and local credentialless health remains usable.

Run all checks executable in the local environment at the relevant checkpoint. If a platform-specific job cannot run locally, record that job as NOT_TESTED. Keep hosted CI as NOT_TESTED until a branch push is explicitly authorized. Do not push just to trigger CI.

**Gate:** Existing CI jobs are not removed, skipped, weakened, or made dependent on a paid/live provider. Hosted CI must pass before final A1 acceptance after a separately authorized push; local success does not substitute for hosted CI.

**Evidence:** Update DEPENDENCY_CHANGES.md, TEST_RESULTS.md, CAPABILITY_PROBES.md, PROVIDER_MATRIX.md, and SECURITY_REVIEW.md with exact versions, OS matrix, exact commands, result counts, synthetic labels, and unverified capabilities.

**Hygiene:** Browser artifacts, coverage XML, DB fixtures, caches, and container volumes stay ignored/temporary. Keep only final approved evidence. Preserve the historical A0 baseline unchanged.

### A1-D — Static Settings proof; mandatory approval stop

#### Task M — Build and review static proof only

**Files:** create docs/proofs/a1-model-settings/index.html, models.css, and final required screenshots. Do not change application Settings code or wire APIs.

**Eight proof states:** Clearly mark all sample names/endpoints illustrative. Include: (1) no connection configured; (2) illustrative installed Ollama models; (3) Router, Chat, and Embedding roles selected; (4) supported, unsupported, and unknown capability states; (5) two independent named OpenAI-compatible connections with exact role-to-connection/model bindings and a configured-key indicator that reveals no key; (6) Local only blocking remote access while a loopback provider remains available; (7) a failed connection with a safe error; and (8) a removed/unavailable connection whose role reference remains visible and requires explicit reassignment.

**Verification:** Use local assets only. Capture the mandatory 1440×900, 1024×768, and 390×844 responsive screenshots. Additionally create one readable contact sheet of the eight named proof states; the failed-connection and unavailable-role states must show their 390×844 mobile presentation. Check 768×1024 and 320×844 for overflow; use keyboard/focus and contrast checks against the approved design; ensure every dimension has no clipped label or horizontal overflow. Keep the three responsive screenshots, one contact sheet, and only individually named source captures that are necessary to make the contact sheet legible. Do not keep redundant viewport variants.

**Gate — hard stop:** Commit the proof and evidence, report A1_UI_PROOF_REVIEW, and wait for explicit owner approval. Do not begin A1-E. No elapsed-time assumption or CI success substitutes for approval.

**Evidence:** Store the proof, three responsive screenshots, eight-state contact sheet, and concise review note only in docs/proofs/a1-model-settings/; add visual dimensions, browser/version, state coverage, and outcomes to TEST_RESULTS.md.

**Hygiene:** Create this one proof directory only because the approved design requires it at A1-D. Remove only temporary screenshots created by this task after final screenshots are verified; preserve historical evidence.

### A1-E — Conditional Settings UI, only after proof approval

#### Task N — Implement approved Settings UI

**Precondition:** Owner explicitly approves the exact A1-D static proof. If approval is absent, stop before editing any frontend application file.

**Files:** update only frontend/index.html, frontend/js/settings.js, frontend/css/styles.css, and the directly relevant existing frontend/browser tests.

**Test-first steps:** Extend existing frontend contract tests for API binding, then browser tests for create/edit/test/remove connection; write-only credential; model list and capability tri-state; per-role connection/model selection; Local only; unavailable saved role; error/success paths; keyboard focus/order, touch targets, contrast, responsive layout, and no horizontal overflow. Test key does not enter DOM persistence, browser storage, logs, or URL.

**Gate:** Every visible control works against authenticated APIs. Remote provider warning/Local only copy is clear. External browser request count remains zero. UI still uses local assets, existing design tokens/fonts, plain JavaScript, and no telemetry or framework.

**Evidence:** Retain the static proof separately; record actual browser test outcomes and screenshot only final regressions needed to prove behavior in TEST_RESULTS.md.

**Hygiene:** Do not create another Settings module, framework scaffold, UI proof directory, or per-control evidence folder. Remove only test-generated artifacts created by the current task.

### A1-F — Final verification and acceptance evidence

#### Task O — Full verification, real-model gate, and final report

**Files:** complete only the required A1 evidence documents in docs/evidence/a1-model-providers/; modify source only if a test exposes a concrete defect and return to its owning task/gate.

**Verification:**

1. Run affected focused tests, the complete backend suite on Python 3.11 and 3.12, complete browser suite, all preserved security tests, source-token scan, git diff --check, frontend checks, Windows compatibility, and container smoke.
2. Confirm captured external browser requests equal zero; report request-guard result.
3. Measure model-free startup, idle memory, dependency install size, frontend asset size, provider discovery latency under deterministic test transport, timeout/cancellation, real local first-token/total latency when an approved model is available, and legacy-model release behavior where measurable. Report measured values or NOT_TESTED; invent no target/result.
4. A real Ollama interaction is blocked until the owner names an already installed model and explicitly authorizes the interaction. Never discover/download/select a model on the owner's behalf. Record exact model/version or digest, endpoint, Local only state, latency, streaming outcome, observed capabilities, and a non-sensitive prompt/response only after authorization.
5. If no OpenAI-compatible server is already running and explicitly configured, mark real integration NOT_TESTED. Anthropic, Gemini, and legacy GGUF may be reported as synthetic only.
6. Report each capability as verified or unknown; distinguish PASS_REAL, PASS_SYNTHETIC, BLOCKED, FAIL, and NOT_TESTED.

**Gate:** A1 is not accepted until the approved proof UI is implemented, all six CI checks pass, security and browser suites pass, keys stay protected, all five network/chat providers plus local embedding compatibility exist, and the owner-authorized Ollama model completes an interaction. Stop for A1 acceptance; do not continue to A2.

**Evidence:** Complete ARCHITECTURE.md, PROVIDER_MATRIX.md, CAPABILITY_PROBES.md, DEPENDENCY_CHANGES.md, SECURITY_REVIEW.md, TEST_RESULTS.md, RESOURCE_MEASUREMENTS.md, REAL_MODEL_RUNS.md, SOURCE_CHANGES.md, and A1_REPORT.md. Preserve BASELINE.md and all A0 evidence unchanged. No duplicate final report.

**Hygiene:** Audit changed, untracked, and task-relevant ignored files; keep only source/tests/config/final evidence; preserve uncertain artifacts and historical A0 evidence; report all remaining artifacts and exact Git status. Do not push or merge.

## Checkpoint hygiene

At the end of every implementation task, include this report:

- New files and new directories; for every directory, why the implementation requires it.
- Existing files modified.
- Temporary artifacts removed, identified by exact path and ownership.
- Unnecessary files remaining, or “none found in the inspected scope.”
- Uncertain files intentionally preserved.
- git diff --check result.
- git status --short --branch and relevant git status --short --ignored -- <paths> output.
- Test-created caches, databases, traces, browser outputs, and dependency artifacts checked without broad deletion.

Never claim a clean repository solely from git status; inspect relevant ignored artifacts too. Do not delete unrelated/pre-existing files or any uncertain item without owner approval.

## Execution handoff

This is a plan only; no application code has been changed by this plan. Review the plan before implementation. When authorizing execution, choose either:

1. Subagent-driven development (recommended): independent provider adapters can be reviewed separately, while persistence, transport, secrets, and integration remain sequential security gates.
2. Native execution: one implementer follows this plan serially and stops at A1_UI_PROOF_REVIEW.

Regardless of execution method, A1-D approval is mandatory before A1-E, and owner-selected Ollama input is mandatory before real-provider acceptance.
