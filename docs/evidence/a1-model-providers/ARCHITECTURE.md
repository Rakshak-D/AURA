# A1-A Contract Architecture

**Status:** Task A evidence. The provider contracts and static provider catalogue are implemented; provider adapters, storage, network transport, model loading, and Settings APIs are not implemented by Task A.

## Contract boundary

The new provider package defines provider-neutral identifiers for the five approved network/chat provider types and the local Sentence Transformers embedding adapter. Model selection is represented by the Router, Chat, and Embedding roles. Structured messages use system, user, assistant, or tool roles; tool messages require a call identity and remain data only.

Provider models, health results, chat requests/results/chunks, and model capabilities use typed values. Every capability starts as unknown; context length is absent until authoritative metadata or a bounded probe establishes it. The static registry describes approved provider identifiers without importing or constructing adapters.

## Safe errors and import behavior

Provider failures normalize to a fixed error category and fixed safe message. Generic timeout and connection failures map to safe categories; unclassified failures become invalid-response errors. Upstream exception text is not retained in the normalized error.

Importing backend.app.providers loads only lightweight contract, error, and registry definitions. It does not import provider adapters, model runtimes, HTTP clients, credential backends, or operating-system credential APIs, and it does not make network connections.

## Deferred A1-A work (as recorded at Task A)

Task B will add AES-256-GCM credential protection and explicit Windows Credential Manager support. Task C will persist user-owned connection, credential, role, capability-cache, and Local only preference records in schema v5. Until those tasks are complete, no model role is persisted or automatically selected. A1-B and later provider/network implementation has not started.

## Task B checkpoint

Task B adds AES-256-GCM credential protection behind an injected key-protector interface. The production protector explicitly selects Windows Credential Manager with local-machine persistence. Credential creation is only available through explicit entry/re-entry; decrypt and startup checks never create or replace a key. Linux and container credential operations fail closed, while credentialless local-provider contexts remain usable. See `DEPENDENCY_CHANGES.md` and `SECURITY_REVIEW.md` for exact package verification and security boundaries.

The secret store persists only encrypted credential records, loads plaintext only into a redacted transient value, and deletes the owner-scoped encrypted row on explicit deletion. Removing a provider connection tombstones the connection and deletes its credential row in the same caller-managed transaction; role references remain. The OS master key is retained because it may protect other connections' credentials.

Task C persistence, schema migration, network transport, provider adapters, model loading, and Settings APIs remain unimplemented. No provider integration has been tested, no model role is automatically selected, and A1-B has not started.

## Task C checkpoint

Schema v5 adds user-owned provider connections, encrypted-credential records, exact role selections, revision-scoped capability cache entries, and a Local only preference. A user may own multiple named connections of the same provider type. Role records bind the role to a connection ID and model ID; the application lookup methods scope by owner, while composite foreign keys prevent cross-owner credential, role, and capability-cache records.

Connection changes advance a configuration revision, so a cache lookup only returns the exact owner's current connection revision and model. Removing a connection sets its tombstone timestamp and deletes its encrypted credential row; role records remain unchanged and resolve as unavailable. The v4→v5 migration does not create role assignments and creates Local only enabled preference rows for existing users. New users resolve to the same enabled default when no explicit preference exists.

`Document.embedding_model_id` is nullable. Existing indexed documents remain null after migration because their stored vectors have no trustworthy model identity; they must be re-indexed before use with a selected embedding model. Migration preserves existing users, tasks, reminders, documents, Chat history, and routine events. The Pydantic `ModelRoleSelectionValue` validates the exact role/connection/model shape without introducing a Settings route.

Task D transport enforcement, provider adapters, model loading, Settings APIs, and A1-B have not started.

## A1-A-R1 correction checkpoint

The provider-neutral chat contracts now carry bounded tool declarations, assistant-proposed calls with provider call IDs, and tool response messages correlated by those IDs. Call arguments remain bounded untrusted JSON text; validation checks only that the payload is a JSON object and does not turn it into an application action. Stream chunks carry partial tool-call deltas keyed by their stream index. No tool execution, registry, or agent loop is included.

Capability values carry an allow-listed evidence source per capability: `controlled_probe`, `provider_metadata`, or `unknown`. Schema v6 stores a separate bounded source value for context length and each capability. The v5→v6 migration only adds constrained source columns; it preserves earlier capability states, roles, connection/model/revision cache keys, and preferences while marking legacy provenance `unknown`. Fresh schema and v4→v6 migration use the same source fields. Provider responses, prompts, credentials, and diagnostic text are not stored in the cache.

## A1-E owner-approved checkpoint

A1-E completes the existing tool-call stream contract with explicit text, tool-fragment, and completion event types and a bounded `ToolCallAssembler`. Assembly validates stable IDs, indexes, cumulative name/argument limits, and final JSON-object arguments. Proposed calls remain inert untrusted data; no application action is parsed or executed.

Linux and container deployments may explicitly configure `AURA_PROVIDER_MASTER_KEY` or `AURA_PROVIDER_MASTER_KEY_FILE` with the base64 encoding of exactly 32 key bytes. The `_FILE` form is preferred with a protected secret mount. The portable protector uses the configured bytes directly for the existing AES-256-GCM record format and derives a stable, non-secret 64-character key ID with keyed SHA-256; it never generates a replacement or falls back to `AUTH_SECRET_KEY`/`SECRET_KEY`. The production factory continues to select Windows Credential Manager on Windows, even when portable variables are present. On Linux, absent or invalid portable configuration fails closed; credentialless local-provider operation remains available.

Environment variables can be exposed by process or container inspection. Operators must protect, retain, and back up the master key separately from the database. Losing or changing the key does not decrypt or rewrite existing records: an unavailable store stays unavailable, and a different valid key reports the existing re-entry state. Windows-protected records are not migrated or decrypted with the portable key. Key rotation is outside A1-E. No schema, dependency, route, adapter, or UI changes are part of this checkpoint.

## A1-F Ollama and OpenAI-compatible adapters

Both adapters accept the existing `ProviderConnectionContext` and use only the injected A1-D `ProviderTransport`. They add no independent HTTP client, dependency, discovery background task, model loader, or model-selection behavior. Ollama uses `/api/tags`, `/api/show`, `/api/chat`, and `/api/embed`; OpenAI-compatible connections use `/models`, `/chat/completions`, and `/embeddings` under the configured path prefix and a single `/v1` segment. Model IDs are sent exactly as selected. An empty discovery response remains empty, and absent models never trigger a download or substitution.

| Provider and feature | Adapter behavior | Model evidence |
| --- | --- | --- |
| Ollama chat and streaming | Structured messages, bounded NDJSON decoding, text deltas, and inert native tool proposals | No model support inferred from chat success |
| Ollama tools and embeddings | Tool declarations/replies map to Ollama function/tool-name fields; embeddings use `/api/embed` and require one finite, nonempty vector | `tools`, `vision`, and `embedding` are reported from `/api/show` only when its capability list is present; context length is reported only for one unambiguous positive metadata value |
| Ollama JSON mode and streaming support | JSON mode sends `format: "json"`; stream parsing requires terminal `done: true` and `done_reason: "stop"` | JSON mode and streaming remain unknown because `/api/show` does not establish those per-model claims |
| OpenAI-compatible discovery/chat/stream/tools/JSON/embeddings | Standard models, Chat Completions, SSE, function-tool, JSON-object and embeddings wire formats | All model capabilities remain unknown; adapter operation support is not evidence of a particular server/model's support |
| OpenAI-compatible unsupported discovery/features | Missing models route is normalized as unsupported discovery; explicit unsupported optional request parameters are normalized as unsupported capability when the bounded error identifies the requested feature | No capability is written or cached by A1-F |

OpenAI-compatible tool call IDs are preserved from the provider. Ollama does not supply stable native call IDs, so the adapter assigns UUID-based IDs for correlation within AURA's inert contract; on the wire, Ollama tool replies are represented by the documented tool name because its message format has no call-ID field. Neither adapter executes proposed calls. OpenAI SSE completion must include both an accepted semantic finish (`stop` or `tool_calls`) and `[DONE]`; truncation, filtering, missing terminal markers, malformed JSON, and unknown reasons fail closed. Ollama emits successful completion only for the documented `done_reason: "stop"` terminal event.

Capabilities are not inferred from model names or successful ordinary chat. Ollama uses provider metadata provenance for allow-listed `/api/show` facts and leaves unreported values unknown; OpenAI-compatible model capabilities remain unknown because no capability metadata or probe is available in this adapter. No controlled probe is run during import, startup, model listing, or ordinary chat.

Response JSON rejects duplicate keys and nonstandard numeric constants. Ollama model listing preserves only bounded ASCII digest, size, and modified-time fields; arbitrary provider metadata is not copied. Streaming frame accumulation is bounded by the existing transport stream cap and a 1 MiB per-frame cap. All HTTP destination, TLS, redirect, proxy, timeout, response-size, duration, concurrency, cleanup, and Local only decisions remain owned by A1-D.

Adapter-level limitations: Ollama's wire format cannot round-trip an AURA call ID; OpenAI-compatible capability support is unknown until a later authorized capability-management stage; vision payloads, provider-specific extensions, and additional incompatible endpoints are not implemented. No provider operation is connected to authenticated Settings or existing Chat until A1-G.
