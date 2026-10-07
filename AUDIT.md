# AURA Technical Repository Audit

Audit date: 2026-10-07. Repository: Rakshak-D/AURA. Revision audited: c15c265 on main, equal to origin/main at audit start.

This audit was performed read-only. No source code, dependency, configuration, generated data, or existing user change was modified. The only intended repository change is this document.

## Executive Summary

AURA is a monolithic FastAPI application with a static vanilla-JavaScript frontend, SQLite/SQLAlchemy persistence, ChromaDB retrieval, a module-global llama.cpp/SentenceTransformers runtime, APScheduler, and an unauthenticated notification WebSocket. The repository is small and syntactically parseable, but it is not currently a reliable or production-safe application.

Verified during this audit:

- There are 39 tracked files, including .env; there is no .env.example.
- Python compileall and AST parsing pass.
- Importing backend.app.main fails in the current environment at import chromadb because the dependency is not installed.
- docker-compose.yml is empty.
- There is one minimal test, tests/test_services.py, and it is not isolated.
- The checkout started clean on main; history shows repeated fix commits but no migration/testing foundation.

What exists structurally: task CRUD, routine CRUD, schedule generation/auto-assignment, chat, upload/list/delete, search, settings, analytics/insights, export, reminders, and a WebSocket route.

What is broken or unsafe: there is no authentication or authorization; every feature assumes user 1; documents are not consistently user-scoped; CORS allows every origin with credentials; the server binds 0.0.0.0; .env is tracked; startup depends on import-time Chroma/model initialization; model paths and environment variables disagree; RAG SQL and vector state can diverge; reminder scheduling does not start at boot and its polling function never delivers or marks notifications; timezone semantics are inconsistent; conflict detection is not concurrency-safe; “streaming” is only frontend typing simulation; search response shapes disagree; and frontend server/model data is inserted with unsafe innerHTML.

The architecture does not need a microservice rewrite. It does need substantial redesign of identity, configuration, temporal data, action execution, RAG ownership, and lifecycle boundaries. Repair incrementally after a short foundation phase. Do not begin feature polish until the app starts deterministically, failures are visible, data is scoped, and tests run without downloading models.

Cannot be verified statically: actual model output quality, Chroma persistence on restart, OCR behavior with Tesseract, browser rendering/accessibility, GPU/native wheel compatibility, and real reminder delivery in a deployed process.

## Current Architecture

backend/run_backend.py starts Uvicorn with reload, port 8000, and host 0.0.0.0. backend/app/main.py configures directories and logging through import-time configuration, creates tables and default user 1 at startup, includes routers, mounts the frontend, and accepts WebSocket clients. Routes directly use SQLAlchemy sessions and services. llm_models.py constructs a global LLM and embedding model during import. database.py constructs a global PersistentClient and Chroma collection during import. Upload stores a SQL document then schedules vector indexing in a FastAPI background task. Reminders use an in-process APScheduler and broadcast to every connected socket.

~~~mermaid
flowchart LR
  Browser[HTML CSS Vanilla JS] -->|HTTP JSON| API[FastAPI monolith]
  Browser -->|unauthenticated text socket| WS[/ws/notifications]
  API --> Routes[API routes]
  Routes --> Services[chat intent schedule routine reminder RAG]
  Services --> SQLite[(SQLite SQLAlchemy)]
  Services --> Chroma[(Persistent ChromaDB)]
  Services --> LLM[llama.cpp Phi-3 singleton]
  Services --> Embed[SentenceTransformer singleton]
  Reminder[APScheduler in process] --> SQLite
  Reminder --> WS
  Upload[UploadFile parser] --> SQLite
  Upload --> Chroma
~~~

The README overstates this architecture: there is no backend streaming route, no one-time event persistence model, no migration system, no complete notification frontend, no real authentication, and no Docker implementation.

## Feature Inventory

| Feature | Classification | Evidence |
|---|---|---|
| Chat | Partially working | /api/chat exists, but routing is heuristic, duplicated, unauthenticated, and model-dependent. |
| Streaming | Broken | chat.js:196-225 simulates typing after complete JSON. |
| Tasks | Partially working | CRUD exists; validation, recurrence, conflicts, deletion, and dates are unsafe. |
| Calendar | Partially working | Timeline is derived from tasks/routines; one-time events are stored as recurring routine rows. |
| Reminders | Broken | Jobs are in memory; scheduler is not started at boot; polling does nothing. |
| Routines | Partially working | Recurring rows work only for valid strings; invalid data can break schedule generation. |
| Scheduling | Partially working | Auto-assignment mutates tasks without locking or reliable priority ordering. |
| Insights | Partially working/misleading | Calculations use naive local timestamps and unsupported “Top 10%” claims. |
| Search | Broken at contract level | Backend returns tasks/knowledge; frontend expects results. |
| Dashboard | Partially working | Errors become plausible empty/safe responses. |
| Settings | Partially working | Single user, weak validation, conflicting defaults. |
| Export | Partially working | Unauthenticated partial export; routines/reminders/vector state omitted. |
| Upload | Broken for production | No enforced size/type controls; indexing asynchronous and non-transactional. |
| RAG | Broken/unreliable | Filename identity, zero-vector fallback, no citations, SQL/vector divergence. |
| Voice | Partially working | Browser Web Speech API only; no backend voice subsystem. |
| WebSocket | Partially working | Global unauthenticated broadcasts, no protocol/backpressure/reconnect, no frontend client. |

## API Audit

All routes are unauthenticated. No route has a current-user dependency. The only rate-limiter decorator is on chat, and limiter application is not configured in main.py.

| Endpoint | Request/response | Frontend caller | Main issues |
|---|---|---|---|
| POST /api/chat | ChatMessage to ChatResponse | chat.js:24 | Saves message in route and process_chat; intent/LLM/RAG; no length bound/auth; errors can leak through result data. |
| DELETE /api/chat/history | envelope | chat.js:317 | Deletes all history for fixed user 1; no history GET exists. |
| GET /api/tasks | list TaskResponse | tasks.js:10 | Malformed JSON tags are skipped; all DB failures return empty list. |
| POST /api/tasks | TaskCreate to TaskResponse | tasks.js:290 | Non-atomic conflict check; mixed datetime semantics; exception text/logging. |
| GET /api/tasks/{id} | TaskResponse | no direct caller | Fixed user; malformed tags can fail. |
| PUT /api/tasks/{id} | TaskUpdate to TaskResponse | tasks.js and chat widget | Cannot clear nullable values; recurring child has no idempotency/end-date check. |
| DELETE /api/tasks/{id} | status object | tasks.js:318 | Broad exception path turns not-found/FK errors into 500. |
| GET /api/tasks/search/{query} | result envelope | no current caller | Unbounded LIKE query and exception details. |
| POST /api/upload | multipart to envelope | upload.js:78 | Parser trusts content type; configured size/extensions unused; SQL precedes background indexing. |
| GET /api/upload/files | envelope | upload.js:114 | Lists all documents; errors return HTTP 200 envelope. |
| DELETE /api/upload/{id} | envelope | upload.js:163 | No user filter; Chroma deletion by filename can delete unrelated chunks. |
| GET /api/schedule | dict | no current caller | Errors become normal error dictionaries. |
| GET /api/analytics | dict | no current caller | days is unbounded; service returns empty dict on error. |
| POST /api/reminders | ReminderCreate to status | no visible caller | Does not persist Reminder or verify task; process-only job. |
| GET /api/search?q= | tasks/knowledge dict | search.js:19 | Documents not scoped; frontend expects data.results. |
| GET /api/export | raw JSON | no current caller | Public personal-data export; user may be null; incomplete data. |
| GET /api/schedule/routine?date= | timeline dict | calendar.js:110 | Generated prep/free blocks; invalid routine strings can fail. |
| POST /api/schedule/auto-assign | result/routine | calendar.js:405 | Mutates backlog without lock/idempotency; priority order wrong/unstable. |
| POST /api/schedule/events | ad hoc dict | no visible caller | Stores one-time event as recurring RoutineEvent; drops date/timezone; negative duration allowed. |
| GET /api/schedule/conflicts | conflict list | no visible caller | Invalid datetimes return 500; timezone mismatch; no edit exclusion. |
| GET /api/insights/focus-score | score dict | analytics.js:22 | Fixed user; zero fallback masks failure; unsupported social comparison. |
| GET /api/insights/trends | Chart.js dict | analytics.js:29 | Fallback masks errors; date generation inconsistent. |
| GET/PUT /api/settings | settings dict | settings.js | No bounds for temperature/name/theme/time; DB/API defaults disagree. |
| GET/POST/DELETE /api/routine... | routine models | no visible caller | Weak validation, fixed user, no conflict handling. |
| WS /ws/notifications | text in, JSON text out | no frontend caller | No auth/origin/protocol/heartbeat/queue/reconnect. |

Contract mismatches: search returns tasks and knowledge but search.js maps data.results; there is no backend stream; upload errors can be HTTP 200; TaskCreate lacks is_flexible although the route checks it; recurring_end_date is not updateable/returned; and chat history cannot be loaded after refresh.

## Database and Data Findings

**DB-01 — Critical — all route functions using user_id=1.** Every personal-data path assumes the default user. Any network client can read, mutate, export, or delete the same data. Evidence: tasks.py:21, chat.py:29, export.py:19-22, settings.py:17, routine.py:26 and equivalent filters. Fix with authenticated current-user dependency, even for a local single-user mode. Architectural change: yes. Regression tests: required.

**DB-02 — High — sql_models.py and task routes.** Duration, priority, tags, recurrence, and dates have weak/no DB constraints; tags are JSON text parsed ad hoc. Malformed state is accepted and later breaks services or is silently skipped. Add typed validation, constraints, and indexes. Architectural: moderate. Tests: required.

**DB-03 — High — database.init_db.** create_all only creates missing tables; it cannot migrate existing schemas. Add Alembic or versioned migrations, backup and upgrade tests. Architectural: moderate. Tests: required.

**DB-04 — High — JSON defaults.** User.settings and ChatHistory.meta_data use mutable Python dictionary defaults without typed shape. Use explicit defaults/copy-on-write or typed JSON models. Tests: required.

**DB-05 — High — task conflict/auto-schedule paths.** Conflict checks and free-slot allocation read then commit without locking. Concurrent requests can reserve the same slot or create overlaps. Add transaction serialization/invariants. Architectural: yes. Tests: required.

**DB-06 — High — all datetime paths.** Browser datetime-local input is converted with toISOString UTC; SQLite stores naive values; services use datetime.now; APIs accept aware and naive values. Events can move dates or raise on comparisons. Establish UTC-aware storage/API and convert only at UI boundaries. Architectural: yes. Tests including DST: required.

**DB-07 — Medium — tasks.py:277-301.** Completing recurring tasks creates children without recurring_end_date or idempotency and approximates monthly as 30 days; null due date can fail. Add occurrence identity/rules. Architectural: moderate. Tests: required.

**DB-08 — Medium — relationships.** Reminder/task, subtask/task, and user relationships lack explicit cascade/restrict policy; SQLite FK enforcement is not enabled. Add explicit policy and integrity tests.

**DB-09 — Medium — settings.** Startup stores light theme while API defaults dark; temperature/reminder time are unvalidated. Use one typed defaults source. Tests: required.

**DB-10 — Low — timestamps.** datetime.utcnow, datetime.now, and browser UTC are mixed. Use one UTC clock policy. Tests: required.

## AI and LLM Findings

**AI-01 — Critical — llm_models.py:14-18,125-130.** Global LLM and embedding models load during import; the exception handler constructs a second LLM. Startup is coupled to native/model availability, retry can allocate twice, and no shutdown/health lifecycle exists. Use lazy/lifecycle-managed services with health state. Architectural: yes. Tests: required.

**AI-02 — High — config.py versus .env.** CONTEXT_WINDOW=4096, LLM_TEMPERATURE=0.3, and N_GPU_LAYERS=-1 are in .env, but Config hard-codes 2048/.1 and ignores N_GPU_LAYERS. Use validated typed settings. Tests: required.

**AI-03 — High — download_models.py versus config.py.** Downloader writes relative models/phi-3..., while config expects backend/models/MODEL_FILENAME. README uses another case/name. Fresh setup can download successfully yet still fallback. Canonicalize path/name and verify checksum. Tests: required.

**AI-04 — High — llm_models.py:112-123.** Embedding failure returns a 384-dimensional zero vector, making retrieval appear successful and assuming all models are dimension 384. Fail closed and validate dimensions. Tests: required.

**AI-05 — High — intent_service.py and chat_service.py.** Keyword heuristics precede the LLM; JSON uses greedy regex; entities are not schema-validated and can create/delete/update state. Use typed output, deterministic dates, allow-listed actions, and confirmation for destructive actions. Architectural: yes. Tests: required.

**AI-06 — High — chat_service.py knowledge/general prompts.** Documents and history are inserted without trust boundaries; knowledge answers may fall back to unsupported general knowledge. Add delimiters, injection-resistant instructions, citations, and uncertainty policy. Tests: required.

**AI-07 — Medium — chat_service.py:68-153,778-790.** User history is saved twice; save failures are swallowed. Use one persistence owner and explicit transaction semantics. Tests: required.

**AI-08 — Medium — chat_service.py:759-763.** Threaded model calls have no semaphore, timeout, cancellation, or queue limit. Add bounded inference concurrency. Tests: required.

**AI-09 — Medium — download_models.py.** No timeout, HTTP status check, checksum, resume, or atomic temp file; embeddings auto-download at runtime, contradicting strict offline claims. Fix reproducible provisioning. Tests: required.

**AI-10 — Low — routine_service.py.** LLM list output is not schema-validated; prep may overlap; all failures become empty list. Use typed validation and visible failure state. Tests: required.

## RAG Audit

Actual path: upload parser -> SQL Document commit -> FastAPI background add_to_rag(filename, content) -> raw character chunks -> global embedding -> Chroma add with filename/chunk metadata -> query embedding/concatenated chunks -> LLM prompt. Search uses Chroma query_texts, a different embedding path.

**RAG-01 — Critical — upload.py:34-40 and rag_service.py.** SQL success is returned before indexing. Crash/model/Chroma failure leaves a visible document with no retrieval; errors are printed and swallowed. Add durable index status/retry/reconciliation or controlled synchronous workflow. Architectural: yes. Tests: required.

**RAG-02 — High — filename identity.** Duplicate detection is global by filename and vector delete filters filename. Same-named documents collide and deletion can remove unrelated chunks. Use document UUID ownership metadata. Architectural: yes. Tests: required.

**RAG-03 — High — parser.py/upload.py.** Configured MAX_UPLOAD_SIZE and ALLOWED_EXTENSIONS are never enforced; MIME is client-controlled; unsupported binary is decoded; PDF/DOCX limits are absent. Add streaming limits, magic/type validation, parser limits, and bounded jobs. Tests: required.

**RAG-04 — High — chat knowledge path.** No source ID, score, citation, or trust boundary is returned. Fix retrieval result objects/citations and grounded answer contract. Tests: required.

**RAG-05 — Medium — rag_service.py:17-29.** Character chunks ignore token/semantic boundaries and no context budget is computed. Use token-aware chunking/budgeting. Tests: required.

**RAG-06 — Medium — search.py:35-49.** Ingestion supplies explicit embeddings while search supplies query_texts; behavior depends on Chroma configuration. Use one explicit embedding strategy and restart/query tests.

**RAG-07 — Medium — deletion ordering.** Chroma deletion precedes SQL commit; failures can leave SQL/vector state inconsistent. Add durable deletion state/reconciliation. Tests: required.

## Scheduling and Calendar Findings

**SCH-01 — Critical — reminder_service.py:59-63 and main.py startup.** Scheduler starts only when schedule_reminder is called; startup never starts it. Restart loses date jobs and polling. Fix startup/shutdown lifecycle. Tests: required.

**SCH-02 — Critical — reminder_service.py:39-57.** check_reminders selects due tasks then does nothing: no notification or sent flag. Public reminder route does not create Reminder rows. Persist idempotent reminders and delivery state. Architectural: yes. Tests: required.

**SCH-03 — High — schedule.py:63-104.** Concrete start/end event becomes weekday/time/duration RoutineEvent, repeats forever, and loses date/end timezone. Separate one-time and recurring events. Architectural: yes. Tests: required.

**SCH-04 — High — schedule_service.py:82-94.** Routine strings are parsed without validation; one malformed row breaks generation. Add constraints and per-row validation. Tests: required.

**SCH-05 — High — schedule_service.py:175-228.** Overlaps are adjusted/hidden, prep blocks can overlap, and no conflict representation is returned. Add shared interval engine. Tests: required.

**SCH-06 — High — auto_schedule_tasks.** Boolean SQL ordering is not a reliable urgent/high/medium/low order and has no tie-breaker. Add numeric rank/deterministic ordering. Tests: required.

**SCH-07 — Medium — conflict checks.** They include generated prep blocks, compare mixed timezone values, and derive next slot from an arbitrary last conflict. Fix shared interval algorithm. Tests: required.

**SCH-08 — Medium — frontend calendar.** UI spans midnight-to-midnight while service free blocks are 08:00-23:00; browser/local/UTC conversion differs. Fix temporal contract. Tests: required.

## WebSocket and Streaming Findings

**WS-01 — Critical — main.py:60-71.** Any client receives every reminder broadcast. Fix authenticated per-user channels. Architectural: yes. Tests: required.

**WS-02 — High — websocket_manager.py:21-30.** Failed sockets are not removed, mutable list is iterated during sends, no bounded queues/backpressure, and thread-safe futures are ignored. Add connection state and queues. Tests: required.

**WS-03 — High — main.py:64-66.** No inbound event schema, max size, close protocol, heartbeat, or reconnect token. Define protocol. Tests: required.

**WS-04 — High — frontend.** No new WebSocket call exists, so notifications have no UI consumer. Wire it or remove the claim. Tests: required.

**WS-05 — Medium — chat.js:196-225.** Simulated intervals are not cancelled; responses can interleave. Implement actual stream/cancellation or remove stream semantics. Tests: required.

## Security Findings

**SEC-01 — Critical — all APIs.** No authentication/authorization; data/export/destructive operations are public. Internet exposure is unsafe. Architectural: yes. Tests: required.

**SEC-02 — Critical — main.py:25-31.** CORS is wildcard with credentials and all methods/headers. Use explicit origins and CSRF policy. Tests: required.

**SEC-03 — Critical — tracked .env.** Current contents show configuration but no obvious secret. Tracking it creates credential/history risk; .gitignore does not untrack it. Rotate any historical credentials and use .env.example. Tests: secret scanning required.

**SEC-04 — High — frontend templates.** marked sanitize is false and model/task/document/search data is interpolated through innerHTML. Stored/reflected XSS is possible. Use safe DOM/contextual escaping and sanitized Markdown. Tests: required.

**SEC-05 — High — uploads/model requests.** No enforced file/body/text/chunk limits, quotas, or timeouts. Add limits and bounded workers. Tests: required.

**SEC-06 — High — errors/logs.** Global and route handlers expose exception strings; logs include user/task content. Use safe public errors and redacted structured logs. Tests: required.

**SEC-07 — High — prompt injection.** Uploaded text/history is untrusted but prompt-injected and can influence action behavior. Use trust boundaries and confirmation. Tests: required.

**SEC-08 — Medium — CDN scripts.** Lucide, Marked, and Chart.js are unpinned CDNs without SRI, conflicting with offline/private claims. Vendor/pin or document network prerequisite.

**SEC-09 — Medium — run_backend.py.** 0.0.0.0 plus reload exposes a development server to the LAN. Default local mode to loopback. Tests: required.

**SEC-10 — Medium — rate limits.** Only chat is decorated; upload/tasks/search/WebSocket are unlimited and limiter integration is incomplete. Add endpoint quotas. Tests: required.

No arbitrary subprocess execution or obvious raw-SQL injection was found. LIKE inputs remain resource/semantic risks.

## Dependency and Environment Audit

requirements.txt duplicates python-multipart and has no lockfile/hashes. Runtime imports psutil but does not declare it; downloader imports requests but does not declare it directly. ChromaDB, SentenceTransformers/Torch, llama-cpp-python, and GPU/CUDA support have native compatibility requirements not documented or tested. USE_GPU=true can fail on CPU-only hosts; N_GPU_LAYERS is ignored. pytesseract does not install Tesseract and OCR is not wired. There is no Python upper bound, OS/ARM64 matrix, model revision/checksum, or reproducible embedding cache. redis, python-jose, passlib, pydantic-settings, and several development packages are unused or partly integrated. No frontend manifest/build lock exists. docker-compose.yml is empty and there is no Dockerfile, volume, healthcheck, or deployment definition.

Do not silently upgrade anything. The conclusion is that the current pinned/native stack is unverified and non-reproducible, not that an upgrade was performed.

## Frontend Audit

**FE-01 — High — chat.js:74-84,112-115,126-167.** Unsafe HTML/Marked rendering enables XSS from server/model/task/file data. Tests: required.

**FE-02 — High — search.js:23-30.** Expects data.results while backend returns tasks and knowledge. Fix shared schema/client. Tests: required.

**FE-03 — High — main.js:4.** Relative /api works only same-origin with backend/reverse proxy; README's separate port workflow fails without base URL/proxy. Tests: required.

**FE-04 — Medium — settings.js:6-7.** window load and DOMContentLoaded both call loadSettings, causing duplicate requests/races. Tests: required.

**FE-05 — Medium — chat/tasks state.** Uncancelled typing intervals, bulk deletes ignoring individual failures, and local mutations without canonical refresh produce stale state. Tests: required.

**FE-06 — Medium — missing callers.** No frontend caller for reminders, export, routine CRUD, dashboard endpoints, or WebSocket. Tests: required.

**FE-07 — Low — accessibility/responsive.** Icon controls rely on titles, modal focus/ARIA behavior is absent, and no browser/accessibility tests exist. Tests: required.

## Documentation, Hygiene, and Testing

README badge says FastAPI 0.110.0 while requirements pin 0.104.1. Clone URL is a placeholder. It claims streaming, citations, memory, Kanban drag/drop, AI scheduling, and privacy/offline behavior beyond source. DATABASE_URL is documented but ignored. Model filename/path differs among README, .env, downloader, and config. RAM guidance is understated. Docker is described but compose is empty. data/ path is wrong relative to runtime. Independent frontend serving breaks relative API calls. WebSocket architecture is not consumed.

Hygiene: .env is tracked; no .env.example; empty compose file; no migrations, lockfile, CI, frontend manifest, checksum metadata; OCR utility is unused; Reminder persistence is unused by reminder route; several schemas/helpers are dead or partial. No model/database/upload artifacts are tracked.

Testing: the only test is a persistent model/Chroma-dependent RAG smoke test that imports app rather than backend.app, writes without cleanup, and cannot run here because chromadb is missing. Missing tests cover startup/config, every API/error status, auth/isolation, DB/migrations/concurrency/timezones, RAG lifecycle/malicious uploads, model outputs/timeouts, scheduler/WebSocket, browser/XSS/accessibility, and deployment.

Prioritized plan: import/startup smoke; temporary SQLite API tests; schema/migration/FK/concurrency/timezone tests; RAG lifecycle/security tests; LLM output/injection/action tests; scheduler/WebSocket tests; browser feature/XSS/mobile/accessibility tests.

## Deployment Audit

Local development is conditional on native dependencies, compatible model, embeddings, and optionally Tesseract. Current environment cannot import the app because ChromaDB is absent. CPU is possible in principle but slow/memory-heavy. GPU is not reproducible. ARM64 is unverified. Windows needs native-wheel/Tesseract validation. Docker is not deployable from this repository. DB/Chroma/uploads/log/model persistence and backups are unspecified. Free cloud deployment must not be assumed.

Conclusion: not deployable as a trustworthy public service. It can become a local single-user application after loopback binding, reproducible provisioning, security boundary, and data/lifecycle repair.

## Critical Findings

1. No authentication/authorization; personal data and destructive operations are public.
2. Wildcard CORS/credentials and 0.0.0.0 development bind.
3. Tracked .env and no safe configuration contract.
4. Import-time Chroma/model lifecycle and clean-environment startup failure.
5. RAG SQL/vector divergence and filename-global deletion.
6. Scheduler not started at boot; reminder checker does not deliver/mark reminders.
7. Stored/reflected XSS through unsafe frontend HTML/Markdown.
8. Inconsistent naive/aware/UTC/local datetime semantics.
9. Unvalidated LLM actions and prompt injection exposure.
10. Incompatible API contracts, fake streaming, and error-as-empty behavior.

## Recommended Target Architecture

Keep a modular monolith. Add typed settings and health checks; Alembic migrations; explicit local/user identity; versioned APIs with current-user dependency and consistent errors; UTC-aware temporal types; separate one-time/recurring events; persisted idempotent reminders; bounded model service; deterministic intent/date parsing plus typed allow-listed actions and confirmation; document/chunk UUIDs and indexing status; explicit Chroma embedding/citations/reconciliation; lifecycle-managed scheduler/WebSocket queues; one frontend API client and safe rendering.

SQLite plus Chroma is sufficient for a single-user local assistant. An in-process bounded worker is sufficient initially; Kubernetes, Kafka, and microservices are not justified.

## Ordered Repair Roadmap

### Phase 0 — Baseline and repository cleanup

Goals: document supported runtime/OS; create non-secret .env.example; establish CI import/compile smoke; decide local-only versus authenticated deployment; audit/rotate historical credentials. Files: README.md, .gitignore, requirements.txt, new CI/config docs. Dependencies: security/product decisions and model revision. Risks: hidden assumptions. Tests: clean checkout install/import/route inventory. Acceptance: explicit prerequisites and no tracked secrets.

### Phase 1 — Foundation/configuration/dependencies

Goals: typed settings, canonical paths, actual env loading, CPU/GPU validation, model checksum, lockfile, lazy model lifecycle, readiness health. Files: config.py, llm_models.py, download_models.py, requirements.txt, run_backend.py. Tests: no-model, CPU, mocked GPU, downloader/path/checksum. Acceptance: documented clean startup.

### Phase 2 — Database/data integrity

Goals: migrations, UTC, constraints/indexes/FKs, typed JSON, recurrence/reminder schema, transaction boundaries. Files: database.py, sql_models.py, pydantic_models.py, task/schedule/reminder code. Tests: migration, rollback, FK, concurrency, recurrence, DST. Acceptance: invariants survive restart/concurrency.

### Phase 3 — API architecture/security

Goals: auth/current-user, explicit CORS, safe errors, body/file limits, quotas, consistent envelopes, loopback-safe defaults. Files: main.py, routes, security.py, frontend API client. Tests: auth/isolation, CORS/CSRF, error disclosure, size/rate limits. Acceptance: no unauthenticated mutation/cross-user access.

### Phase 4 — LLM/intent/action system

Goals: bounded inference, timeouts, structured output, deterministic dates, allow-listed actions, confirmations, prompt trust boundaries, single history path. Files: chat_service.py, intent_service.py, llm_models.py, schemas. Tests: malformed output, injection, ambiguity, duplicates, timeout/concurrency. Acceptance: model cannot perform unvalidated actions.

### Phase 5 — RAG

Goals: document UUID/ownership, validation/limits, bounded index jobs, status/retry/reconcile, explicit embeddings, citations, safe delete. Files: upload.py, parser.py, rag_service.py, database.py, chat/search/upload JS. Tests: file types, malicious/oversized inputs, failure/restart/delete/duplicates/injection. Acceptance: SQL/vector state recoverable and answers cite sources.

### Phase 6 — tasks/calendar/reminders/routines

Goals: interval model, one-time/recurring separation, deterministic conflict engine, locked auto-scheduling, persistent reminders, UTC calendar. Files: task/schedule/routine/reminder routes/services/models and JS. Tests: intervals, recurrence, DST, concurrent schedule, restart delivery. Acceptance: no tested duplicate/overlap and reminders recover.

### Phase 7 — WebSocket/streaming/voice

Goals: real server stream or remove claim; authenticated socket protocol/heartbeat/queue/reconnect; explicit browser-only voice or tested backend voice. Files: main.py, websocket_manager.py, reminder service, chat.js, voice.js. Tests: auth/reconnect/disconnect/slow consumer/per-user delivery/cancel. Acceptance: private bounded notifications consumed by UI.

### Phase 8 — Frontend stabilization

Goals: shared API contracts, safe DOM/Markdown, correct search/upload shapes, canonical refresh, focus/ARIA/mobile behavior. Files: frontend JS, index.html, styles.css. Tests: browser flows and XSS fixtures. Acceptance: every visible feature has a caller/loading/error state and safe rendering.

### Phase 9 — Testing/CI

Goals: isolated fixtures and API/DB/RAG/AI/scheduler/WebSocket/browser/security suites. Files: tests and CI. Tests: deterministic mock CPU CI plus marked integration. Acceptance: clean repeatable CI.

### Phase 10 — Deployment

Goals: if desired, Dockerfile/compose, persistent volumes, health checks, backups, secrets, resource limits, TLS/reverse proxy, operational docs. Files: Docker/config/startup/README. Tests: clean deployment and backup/restore. Acceptance: documented local CPU deployment and reviewed public deployment.

## Final Status

Unique finding counts from the explicitly labeled findings in this document: Critical 9; High 27; Medium 18; Low 3.

Git status at audit start was clean: main...origin/main. Compile/AST checks passed. No source file was modified. .env is tracked; its current visible contents contain configuration but no obvious secret assignment. No model/database/upload artifact is tracked.

Local safety: not safe on a shared network; only suitable for tightly controlled localhost experimentation after dependencies are installed and model/RAG behavior is understood.

Public exposure: not safe.

Recommended first repair phase: Phase 0 immediately followed by Phase 1, with Phase 3 security work a release blocker.

Top ten blockers: the ten items under Critical Findings.
