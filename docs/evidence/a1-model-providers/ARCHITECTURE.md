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

Task C persistence, schema migration, network transport, provider adapters, model loading, and Settings APIs remain unimplemented. No provider integration has been tested, no model role is automatically selected, and A1-B has not started.
