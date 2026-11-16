# AURA A1 — Model-Agnostic Provider Layer

| Field | Value |
|---|---|
| Status | Proposed; awaiting owner approval |
| Milestone | A1 only |
| Repository | `Rakshak-D/AURA` |
| Branch | `feat/a1-model-providers` |
| Design base | `9e98b50387c9149fb2bbe59380fc6c4618d6c065` |

## Purpose

Replace AURA's single in-process GGUF path with an authenticated, provider-independent model layer. A1 adds five provider adapters, user-scoped provider and role settings, capability reporting, provider-level streaming, secure credential storage, server-enforced Local only mode, and migration of existing model call sites. The existing authenticated Chat API and strict action validation remain compatible.

This document is the proposed architecture for review. No product code or Settings UI has been implemented. The complete staged sequence and acceptance checklist are included below so this document can be used without the original request. The static Settings → Models proof is a separate approval gate; the UI itself must not be implemented before that proof is approved.

## Goals and boundaries

- Support Ollama, OpenAI-compatible APIs, the existing optional in-process GGUF runtime, Anthropic, and Gemini through one provider-independent contract.
- Configure exactly three model roles: Router, Chat, and Embedding.
- Describe provider and model capabilities as verified supported, verified unsupported, or unknown/untested. Never guess context length or infer capability from a model name.
- Enforce Local only at the shared outbound transport boundary for discovery, health checks, capability probes, chat, streaming, and embeddings.
- Store provider credentials encrypted at rest, outside `User.settings`, and keep them out of responses, logs, prompts, browser storage, and diagnostic evidence.
- Preserve the current `/api/chat` request and response contract, authentication, ownership checks, action validation, model-free handling, and local-first defaults.
- Keep model loading lazy and avoid loading Router and Chat models simultaneously merely because both are configured.
- Implement provider streaming at the adapter layer only. A1 does not add a Chat streaming UI or an agent-event stream.

Out of scope: tool execution or agent planning, the A2 date/command parser, approval cards, React/TypeScript/Vite, dashboard redesign, A4–A6 integrations, deployment, and any model download or silent model substitution. AURA must not start a provider server or download a model as part of setup or testing.

## Verified repository facts

The A1 branch is based directly on the expected A0 merge commit. The baseline evidence is recorded in [`docs/evidence/a1-model-providers/BASELINE.md`](../../evidence/a1-model-providers/BASELINE.md).

- The backend is FastAPI with SQLAlchemy and SQLite; the frontend is vanilla JavaScript.
- `backend/app/models/llm_models.py` exposes a lazy `llm.generate(prompt, ...)` and `llm.embed(text)` singleton. It loads optional llama.cpp and sentence-transformers only when called.
- Direct inference calls exist in Chat, intent classification, routine parsing, and RAG embedding code. Runtime diagnostics also report the fixed GGUF/embedding setup.
- Intent, Chat, and routine code contain model-specific prompt formatting. All application-side special-token construction and stop-token cleanup must be removed.
- The authenticated `POST /api/chat` response has `response`, `action_taken`, `data`, and `suggestions`; the existing browser client consumes that shape.
- `User.settings` is returned by Settings APIs and `/api/export`; provider secrets and model credentials therefore must be persisted outside that JSON field.
- SQLite backup copies database rows. Under the selected OS-bound recovery policy, those rows may include ciphertext, while the encryption master key remains in Windows Credential Manager. Moving a backup to another Windows profile or machine requires re-entering provider keys.
- Existing action handling uses strict Pydantic validation and server-side ownership/confirmation checks. These are invariants, not migration targets.
- A0 tests check startup laziness and include browser, authentication, network, and AI security coverage.

## Proposed architecture

### Provider contract and service boundary

Introduce a typed provider protocol in a small backend provider package. It accepts ordered structured messages with `system`, `user`, `assistant`, and conditionally `tool` roles. It returns normalized chat results, async stream chunks, embeddings, model lists, health results, and capability records. Adapters alone serialize the messages into provider-native payloads; application services never construct model-specific control tokens.

A registry maps the supported provider identifiers to adapters. A per-user model service loads a user's persisted provider configuration and role selection, resolves the role according to the fallback rules below, and invokes the adapter. Provider operations all pass through one shared policy-enforcing transport. It owns endpoint validation, outbound policy, timeouts, redirect handling, response size bounds, safe error normalization, and sanitized request metadata. Adapters do not open sockets independently.

Provider failures normalize to safe categories: unavailable, authentication failed, model not found, unsupported capability, timeout, Local only blocked, endpoint blocked by destination policy, connection removed/unavailable, secure secret store unavailable/re-entry required, invalid response, rate limited, or incomplete configuration. User-facing errors contain no stack traces, raw URLs with credentials, response bodies, or secret values.

### Capabilities and probes

Each capability record includes provider and model identifiers, context length when authoritative, tool/JSON/vision/stream/embedding support, and a verification state. Each individual capability has an explicit supported, unsupported, or unknown state; missing provider metadata remains unknown. Context length is absent/unknown unless documented metadata provides it.

Health and capability checks run only on an explicit user request or the first explicit use that requires the relevant capability. Bounded non-destructive probes are cached per user and keyed by connection ID, provider configuration revision, endpoint, and model. A configuration change invalidates only that connection's cache. Probe records contain safe summaries and timestamps, not credentials or prompt content. A tool-support probe never executes a real tool. No response from a Chat call alone proves tool, JSON, vision, or embedding support.

### Adapters

| Adapter | Native responsibilities and constraints |
|---|---|
| Ollama | Use its native model listing, chat/stream, and embedding endpoints. List installed models only. Never pull, replace, or start a model on the user's behalf. Capabilities stay unknown unless provider metadata or a bounded probe verifies them. |
| OpenAI-compatible | Use a configurable base URL and standard model/chat/embedding routes where present. Handle missing/incomplete model discovery with explicit manual model-ID entry. Treat optional features as unknown unless verified for that server/model. |
| Legacy GGUF | Preserve the optional local runtime and configured model path. Use llama.cpp's supported chat-format or tokenizer-template mechanism. Remain lazy, release the active legacy model when switching away where supported, and report incompatibility if the template cannot safely represent structured messages. |
| Anthropic | Use documented Messages payload and authentication conventions. Treat model discovery as provider-supported or manual-entry according to the current API; do not emulate OpenAI format. Report only verified capabilities. |
| Gemini | Use documented Gemini request, authentication, model-discovery, and streaming conventions; do not emulate OpenAI format. Report only verified capabilities. |
| Local Sentence Transformers embeddings | Preserve the existing explicitly provisioned sentence-transformers embedding runtime as a local, Embedding-only adapter. Use only the configured on-disk model; never download or scan for another model. It does not provide Chat, Router, or streaming. |

Use a direct maintained HTTP client for network adapters rather than a model/agent framework. AES-GCM is provided by the established `cryptography` package. Exact pinned runtime versions and installed-size measurements are implementation outputs and must be recorded before acceptance. No LangChain, LangGraph, or similar framework is introduced.

The five network/chat adapters above are the required provider set and stay in the specified order. The local Sentence Transformers adapter is a compatibility path for the existing RAG embedding call, not a sixth general-purpose Chat provider.

### Model roles and resource policy

Persist a provider/model assignment for each of Router, Chat, and Embedding. If Router is unset, it may resolve to the configured Chat model. If Embedding is unset, it may resolve to Chat only when that selected Chat model has verified embedding support; otherwise report embeddings unavailable. Unknown support is not sufficient for fallback. No other implicit model substitution is allowed.

The provider service does not load models at startup. It loads a role's model only on an explicit use. Local in-process GGUF transitions are serialized and reuse at most one active heavy model where supported. External servers such as Ollama own their own residency; AURA reports that limitation and does not claim to unload a remote server's model. Settings choices are never changed automatically for memory reasons.

### Persistence and authenticated settings

Add user-owned relational records for named provider connections, role selections, Local only preference, encrypted credentials, and private capability cache entries. A user may save multiple named connections for each provider type; at minimum, multiple OpenAI-compatible connections are required. Each connection has its own base URL, credential, model list, configuration revision, and capability cache. Enforce `(user_id, connection_id)` ownership on every read, write, probe, and invocation; never resolve a connection by ID alone. Capability cache keys include the owning user, connection ID, configuration revision, and model ID, so connections and users cannot share cached results.

Each role selection stores a specific `provider_connection_id` and `model_id`, not just a provider type. Router, Chat, and Embedding may independently point to different named connections, including distinct OpenAI-compatible connections for different roles. The API must verify the connection belongs to the authenticated user when a role is selected. Editing a connection does not change its ID or silently choose a different model; invalidate that connection's capability cache and keep the saved role reference. If the selected model is no longer available, report that role as unavailable and require an explicit user change. Removing a connection soft-deletes/tombstones its record and removes its stored credential, but preserves any role reference to that connection ID/model ID; return a clear connection-removed error until the user explicitly clears or reassigns the role. Never auto-migrate or reassign roles on edit or removal. Do not serialize provider records through `User.settings` or existing generic Settings update merging. API request models are strict and credential fields are write-only; reads may return `has_api_key`, never the key or ciphertext.

The model settings API will be authenticated and user-scoped. It must expose provider types, configure/remove a connection and credential, list models, set role selections, test a connection, read safe capability summaries, and read/update Local only. Preserve existing Settings routes and the Chat API schema. The implementation can follow the repository's existing route naming conventions; that naming does not change the required behavior or security boundary.

On migration, create no active Chat, Router, or Embedding assignment automatically. Keep existing configured GGUF and sentence-transformers paths available as candidates, but require the user to select and save a role in Models before inference uses them. This preserves existing paths without silently choosing a model or treating a manifest default as the owner's selection. Until a role is chosen, Chat uses its explicit no-model fallback; Local only remains enabled.

### Credential protection and recovery

Owner-selected policy: **OS-bound recovery**. Encrypt each provider secret with AES-256-GCM using a random 96-bit nonce and a separately protected master key. Store nonce, ciphertext, tag, and format version in a dedicated credential record, never plaintext. Bind ciphertext with authenticated additional data to its user and credential identity so rows cannot be reassigned across users without decryption failure.

**Windows:** A1's supported runtime secret store is Windows Credential Manager under the same Windows account that runs AURA. Store the 256-bit master key as a generic credential through the native Windows `CredWrite`/`CredRead` APIs; store only AES-GCM ciphertext for provider keys in SQLite. Do not store the master key in a file, environment variable, registry entry, database, or application settings. The expected recovery path is the same Windows account/profile on the original machine. A changed service account, new Windows profile, profile reset, machine migration, or missing Credential Manager entry is not assumed recoverable, even if the account name is the same. Do not rely on roaming-profile behavior. Windows Credential Manager protects credentials using the user's logon-session protection; DPAPI likewise normally requires matching user credentials and the same machine. AURA's documented support is intentionally narrower than any OS-managed roaming option. Windows containers are unsupported for credential operations unless the native user credential vault is genuinely available to the AURA process; otherwise they fail closed under the unavailable-store rule.

**Linux and containers:** A1 does not claim that Windows Credential Manager is available in Linux or a container and does not add a Linux secret-store implementation. Production credential save and use on Linux/headless/container runtimes return `secure_secret_store_unavailable`. No environment-variable, file, or plaintext fallback is permitted. Linux CI may use a test-only injected fake key protector for deterministic encryption tests; that fixture must not be selectable by production settings or packaged runtime. Unauthenticated local providers such as loopback Ollama and the existing local model adapters remain usable.

**Unavailable or locked store:** If the native key store cannot be opened, the backend fails closed for credential creation and decryption/use. Preserve ciphertext and configuration, expose a safe `needs_reentry`/store-unavailable state, and do not overwrite an existing master key or reinterpret old ciphertext as plaintext. If the OS store is working but the expected AURA master-key entry is absent and ciphertext already exists, do not silently generate a replacement at startup. Generate a new OS-protected master key only after explicit credential re-entry; replace ciphertext only for the connection whose owner re-enters its key, and keep other connections marked `needs_reentry`. Operations that need no credential, including local providers, remain available. Decrypted keys exist only transiently in backend memory for a request and are never included in logs, exceptions, model messages, browser storage, or response bodies.

**Backup and restore:** SQLite backups include provider metadata and encrypted credential blobs, not the master key or a Credential Manager export. `/api/export` excludes provider configuration secrets and ciphertext. Restoring the database under the original Windows account/profile on the original machine can decrypt credentials only while the matching Credential Manager entry is still present. Restoring on another machine/profile, after Windows/profile reset, or without that entry leaves the credential blobs undecryptable; AURA must show `needs_reentry`, not silently create a replacement key that masks the condition.

**Re-entry after migration:** Start AURA under a supported Windows account, restore the SQLite backup if applicable, and open each affected named provider connection. The UI prompts for a replacement API key without pre-filling the old one. The owner types the key again; the backend encrypts it using the current OS-protected master key, replaces that connection's ciphertext, and reports only a safe `has_api_key`/connection-test state. Repeat for each connection. Re-entry does not alter role assignments or model IDs. If the user cannot provide a key, that connection and any role pointing to it remain unavailable with a clear error. Security evidence must cover same-profile restore, missing-key state, re-entry, and non-disclosure.

### Local only and outbound request policy

Local only defaults to enabled per user, including a migration-safe default for existing accounts. Every provider operation reaches the shared transport, which checks the stored policy and destination before connecting. Endpoint protection applies in both Local only and remote-enabled modes.

**Local only enabled:** Permit only explicitly validated loopback endpoints: literal loopback IPs or `localhost` whose entire resolution set is loopback. Allow loopback Ollama/OpenAI-compatible local servers over HTTP or HTTPS. Reject all non-loopback destinations, including private/LAN and link-local addresses.

**Remote enabled:** Continue to allow explicit loopback providers independently of cloud configuration. Treat a literal loopback IP or exact `localhost` name as local, never as a remote/cloud destination. Do not treat an arbitrary provider hostname that resolves to loopback as a local endpoint; reject it as loopback-as-remote. Permit non-loopback endpoints only over HTTPS and only when every resolved address is a globally routable unicast address outside the IANA IPv4/IPv6 special-purpose registries. Block private, shared-address, link-local, loopback-as-remote, unspecified, multicast, reserved, documentation, translation, and other non-global/special-use ranges. Use the IANA registries as the maintained range source; do not rely only on a language runtime's `is_private` property. Explicitly block known cloud metadata addresses and hostnames, including IPv4 metadata endpoints such as `169.254.169.254`, `169.254.170.2`, and Alibaba `100.100.100.200`, AWS IPv6 `fd00:ec2::254`, Google IPv6 `fd20:ce::254`, and `metadata.google.internal`; the general special-use range rules apply as well. A cloud hostname resolving to any blocked address is rejected even if other answers are public.

Parse endpoints strictly: reject URL credentials, malformed/ambiguous authorities, unsafe schemes, and unsupported address encodings. Normalize IPv4-mapped IPv6 before policy classification. Resolve hostnames at connection time, reject empty or policy-mixed/ambiguous answer sets, validate every answer under the active policy, and connect only to one of those exact validated numeric destinations while preserving the configured host for TLS certificate validation and HTTP Host. Multiple answers are acceptable only when all pass the same destination policy; never select an allowed address from a mixed allowed/blocked set. Do not validate one DNS answer and then let the HTTP client resolve the hostname again. Revalidate on each operation so DNS changes cannot move an existing connection to a blocked address. Disable automatic redirects; any redirect is a safe provider error and must not contact its target. Disable ambient proxy inheritance so environment proxy variables cannot route a validated request elsewhere. Enforce this boundary for discovery, health checks, capability probes, chat, streaming, and embeddings before provider traffic; direct API calls cannot override it.

The Settings proof and final UI must plainly state that remote inference sends the submitted message to the configured provider and require an intentional Local only change before remote use. For remote requests, include only the current user message and minimal system instruction. Omit chat history, task data, profile information, RAG results, local documents, and other personal context. A1 has no additional-context consent flow. Store only sanitized outbound metadata (provider/model identifiers, operation, timing, outcome); never store raw prompts or credentials. Untrusted provider/model text cannot authorize an external action.

### Existing service migration

- Migrate Chat call sites to structured provider messages while preserving current task/reminder paths, no-model fallback, response fields, and action semantics.
- Keep the current server-side Chat routing and handler decisions. Model output remains a proposal only: existing strict action parsing/validation, authenticated user identity, ownership lookups, and destructive-operation confirmation remain authoritative. Provider-native tool calls are not executed in A1. No action handler is rewritten as an agent loop.
- Pass authenticated user identity into model selection, including intent classification and embedding operations. Audit routine parsing and tests even if no production caller is found.
- Migrate RAG embedding calls through the Embedding role and preserve the current local Sentence Transformers path as an explicitly selectable local embedding adapter. Keep retrieved local context out of remote provider requests; a remote model request contains only the active user message and minimal system instruction. Local task/reminder/schedule handlers still read the authenticated user's data server-side. If a remote model is selected for a knowledge question, do not attach local documents, history, tasks, or profile data; report when local document context is unavailable.
- Track the embedding provider/model identity for indexed vectors. Do not query vectors with a different embedding model or dimensionality. When a user changes the Embedding selection, report that existing documents require re-indexing before they can be searched with the new model; do not silently mix vector spaces.
- Replace provider-specific status in runtime diagnostics with safe, non-loading provider configuration/readiness summaries. Startup remains free of model load, provider probing, and network traffic.
- Remove all hard-coded model-specific tokens, stop lists, and cleanup from `backend/`. Add a CI test scanning all backend application files for the prohibited role/end token strings; do not evade it through encoded or dynamically assembled tokens.
- Preserve all existing authentication, strict nine-action types, validation, ownership checks, confirmations, and AI security tests. A1 adds no tool execution loop.

## Settings proof approval gate

After backend work and before implementing the Settings UI, create static HTML/CSS proofs under `docs/proofs/a1-model-settings/`. The proof demonstrates: no provider connected; illustrative Ollama models; selected Router, Chat, and Embedding roles; supported/unsupported/unknown capability states; at least two named OpenAI-compatible connections with distinct illustrative endpoints and credential indicators; roles independently assigned to particular connection/model pairs; Local only blocking a remote provider while a loopback provider remains available; a failed connection; a removed/unavailable connection that leaves its role assignment visible and requires explicit reassignment; and a configured key without revealing it. Label sample providers/models/endpoints as illustrative. Use local assets only.

Capture 1440×900, 1024×768, and 390×844 screenshots; check 768×1024 and 320×844 for overflow. At that point stop with `A1_UI_PROOF_REVIEW`. Do not wire or implement the Settings UI until the owner approves the proof. After approval, the vanilla-JS interface implements every control and connects to the actual authenticated API.

Follow the existing AURA design bible and frontend structure; prepare model settings without redesigning the application or creating a generic settings dashboard. Reuse the established dark tokens (`#0B0F19`, `#151B2B`, `#E2E8F0`, `#5EEAD4`, `#A78BFA`, `#FB7185`, `#F59E0B`, `#34D399`) and self-hosted Sora, Inter, and JetBrains Mono. Keep the existing no-CDN policy and add no animation library. Use plain labels including “Choose a model”, “Test connection”, “Keep everything on this device”, “Currently using”, “This model cannot use tools”, and “No models found”. Explain technical terms only where needed.

The final UI must have mobile body text of at least 16 px, touch targets at least 44×44 px, text contrast of at least 4.5:1, interactive contrast of at least 3:1, visible keyboard focus, logical tab order, no keyboard traps, clear success/error states, no clipped labels, and no horizontal overflow. The proof must demonstrate the eight required states listed above; illustrative names/data must be visibly marked and never become application defaults.

## Staged execution and CI

1. **A1-A — Baseline and architecture:** verify Git/worktree state, inventory all model dependencies and call sites, define provider/capability contracts, and document endpoint and credential protection.
2. **A1-B — Backend providers:** implement Ollama, OpenAI-compatible, legacy GGUF, Anthropic, and Gemini adapters; roles; capability handling; Local only enforcement; and authenticated model Settings APIs.
3. **A1-C — Existing service migration:** migrate Chat, intent, and embedding calls; remove model-specific formatting; preserve strict actions and model-free behavior; add regressions.
4. **A1-D — Static interface proof:** create the proof and screenshots, then stop at `A1_UI_PROOF_REVIEW`.
5. **A1-E — Settings UI:** only after owner approval of A1-D, implement the approved vanilla-JavaScript UI, connect every control to the API, and verify accessibility, responsiveness, and real provider selection.
6. **A1-F — Final verification:** run backend/browser/security checks, owner-selected real Ollama interaction, conditional OpenAI-compatible integration, performance measurements, evidence, and report. Stop for A1 acceptance; do not start A2.

Preserve all A0 CI jobs: Linux Python 3.11, Linux Python 3.12, Windows Python 3.12, frontend syntax/security, Playwright browser regressions, and container smoke tests. Extend relevant jobs without weakening or removing existing jobs. CI must not require Ollama, downloaded models, GPUs, paid credentials, or live cloud connectivity. Use deterministic controlled transports. Document and test any platform-specific dependency restriction.

Keep frontend dependencies local and add no telemetry. Measure model-free backend startup, idle memory, runtime dependency installation size, provider discovery latency, real local-model first-token and total latency where measurable, timeout/cancellation behavior, and whether the legacy model remains loaded after switching. Measure added frontend asset sizes. Do not claim a target without a measurement; if no animation is added, report that instead of fabricating frame-time evidence.

## Verification and acceptance

Use controlled fake transports for deterministic tests of all adapters, provider streaming/cancellation, timeouts, normalization, discovery, role fallback, capability cache invalidation, connection isolation, and endpoint policy in both Local only and remote-enabled modes. Do not call real cloud endpoints or include real secrets in automated tests. Explicitly test: DNS rebinding between configuration and connection and between separate requests; pinning to the exact validated address; mixed public/private DNS answers; IPv4-mapped IPv6 loopback and private/metadata addresses; redirect attempts from loopback and public HTTPS to blocked destinations; private, shared-address, link-local, loopback-as-remote, reserved, multicast, unspecified, and documentation ranges; and metadata targets `169.254.169.254`, `169.254.170.2`, `100.100.100.200`, `fd00:ec2::254`, `fd20:ce::254`, and `metadata.google.internal`. Verify valid public HTTPS and explicit literal-loopback/`localhost` behavior in both policy modes, and confirm no ambient proxy use. Record attempted connection targets to prove blocked cases make no socket connection. Test every provider operation, including embeddings, streams, discovery, health checks, capability probes, and direct API calls. Verify per-user named-connection ownership, distinct base URLs/credentials/cache/model IDs, and that edit/removal leaves roles pointing to the original connection/model and returns an unavailable error without reassignment. Verify encrypted-at-rest storage, Windows Credential Manager recovery states, Linux/container credential fail-closed behavior, re-entry, and absence of secrets in settings/export/logs/errors/prompts. Preserve current A0 security invariants and startup laziness; keep security tests intact.

Run the affected tests, full backend suite on Python 3.11 and 3.12, and all browser tests after UI implementation. Browser requests to non-local/external hosts must be captured and remain zero. Report synthetic and real evidence separately with `PASS_REAL`, `PASS_SYNTHETIC`, `BLOCKED`, `FAIL`, or `NOT_TESTED`.

No model may be downloaded or selected by the implementation engineer. Final A1 acceptance requires all of the following: the provider abstraction and all five required provider adapters exist, plus the local embedding compatibility adapter; provider streaming works; roles persist; capabilities distinguish verified/unknown; configuration is authenticated and user-isolated; keys are encrypted at rest and absent from responses/logs; Local only is server-enforced; forbidden model-specific tokens are absent; Chat/intent use native structured messages; existing actions and ownership checks pass; no-model Chat works; the Settings design is approved and every control works; browser, backend, and security suites pass; at least one real owner-selected Ollama model completes Chat and is visible in the UI; no model is silently downloaded/substituted; dependency/asset sizes are reported; and no A2 behavior was added.

Run a real Ollama interaction only with an installed model explicitly selected by the owner; record exact provider/model/version-or-digest, endpoint, Local only state, latency, stream outcome, observed capabilities, and a non-sensitive test prompt/response. If an OpenAI-compatible server is not already available and explicitly configured, report it as `NOT_TESTED`; Anthropic, Gemini, and legacy GGUF may use clearly labeled synthetic adapter tests. No real provider integration is claimed by this design or baseline.

The required Ollama target is a later owner input. Do not discover or choose a model on the owner's behalf for acceptance. Provider implementation and synthetic tests can proceed without that input, but the real-provider acceptance criterion remains blocked until the owner selects an installed model and authorizes the real interaction.

Measure model-free startup, idle memory, dependency install size, frontend asset size, connection latency, first-token/total real model latency where available, timeouts/cancellation, and legacy model release behavior. Report dependency and asset sizes and every unverified adapter capability. For final reporting, include repository/commit/push/PR state, architecture and secret/policy behavior, a provider-by-capability matrix with real-versus-synthetic status, exact test commands/results/runtime versions, measurements, visual evidence, blockers, and the required stop declaration. A1 is not complete until the checklist above is met; stop at the static proof approval boundary when reached.

## Important risks and controls

| Risk | Control |
|---|---|
| SSRF, redirects, proxy configuration, or DNS rebinding bypass endpoint policy | Central transport applies destination policy in both Local only and remote-enabled modes; validates and pins numeric destinations at connection time; blocks non-global and metadata destinations; no redirects or ambient proxies; controlled DNS/redirect tests verify blocked attempts never connect. |
| Role silently changes when a named connection changes or disappears | Store connection ID and model ID per role; soft-delete removed connections; preserve references; return an unavailable error until the user explicitly edits the role. |
| Credential exposure through broad Settings JSON, logs, or backup/export | Separate user-owned credential table; AES-GCM; Windows OS-protected master key; write-only API; no credential fields in logs/prompts/export; explicit restore/re-entry procedure. |
| Guessing provider capabilities | Per-capability tri-state, authoritative metadata or bounded probes, user-scoped cache, no inference from model names. |
| Existing local context reaches cloud providers | Remote message contains only the active user message and minimal system instruction; no RAG, tasks, history, or profile context. |
| Memory spikes from duplicate local models | Lazy load, serialized legacy transitions, at most one active in-process heavy model where possible, external residency limitation disclosed. |
| Model-specific formatting returns through a service helper | Provider-only native serialization and mandatory backend source scan. |
| OS key store absent or inaccessible | Windows Credential Manager is the only production secret-store backend in A1. Linux/container credential operations fail closed; test-only fake protectors cannot be enabled in production; local unauthenticated functionality remains available. |

## Repository hygiene

Keep permanent AURA source, tests, documentation, configuration, and final evidence inside this repository. Reuse existing backend, flat `tests/`, frontend, and `docs/evidence/a1-model-providers/` locations. The small `backend/app/providers/` package is justified by the independent provider adapters and shared policy/secret handling; do not add generic framework layers or per-feature folders. Create `docs/proofs/a1-model-settings/` only at the A1-D visual-proof stage. Do not create placeholder files or duplicate evidence directories.

At every implementation checkpoint, inspect changed, untracked, and task-relevant ignored files; remove only clearly identified disposable files created by that stage. Preserve historical evidence, licences, security tests, user data, models, secrets, worktrees, and anything with uncertain ownership. Keep caches, virtual environments, databases, credentials, and intermediate test traces out of Git. Run `git diff --check` and report created/modified files, necessary directories, disposable artifacts removed, uncertain files preserved, remaining unnecessary artifacts, and exact Git status. Do not push, merge, deploy, or begin A2/A3.

## References

- A1 implementation request: user-provided `AURA — A1 Model-Agnostic Layer` specification.
- Existing security invariants: [`docs/ai-security.md`](../../ai-security.md) and A0 evidence in `docs/evidence/a0-foundation/`.
- AES-GCM API and nonce requirements: [cryptography AESGCM documentation](https://cryptography.io/en/stable/hazmat/primitives/aead/).
- Windows Credential Manager and user-scoped secret protection: [Microsoft password handling guidance](https://learn.microsoft.com/en-us/windows/win32/SecBP/handling-passwords) and [CryptProtectData documentation](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata).
- Keyring backend selection and Windows backend reference: [keyring documentation](https://keyring.readthedocs.io/en/stable/) and [Windows backend source](https://github.com/jaraco/keyring/blob/main/keyring/backends/Windows.py).
- Gemini API reference: [Google Gemini API](https://ai.google.dev/api/generate-content?hl=en).
- IP destination classification and special-use ranges: [IANA IPv4 Special-Purpose Address Registry](https://www.iana.org/assignments/iana-ipv4-special-registry) and [IANA IPv6 Special-Purpose Address Registry](https://www.iana.org/assignments/iana-ipv6-special-registry).
- Cloud metadata endpoint references: [AWS EC2 IMDS](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html), [Google Compute Engine metadata server](https://docs.cloud.google.com/compute/docs/metadata/overview), [Azure IMDS](https://learn.microsoft.com/en-us/azure/virtual-machines/instance-metadata-service), [Oracle Cloud instance metadata](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/gettingmetadata.htm), and [Alibaba Cloud metadata](https://www.alibabacloud.com/help/en/ecs/user-guide/view-instance-metadata/).
