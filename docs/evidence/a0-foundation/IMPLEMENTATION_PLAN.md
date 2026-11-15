# AURA A0 Foundation Implementation Plan

> **For agentic workers:** Execute task-by-task. Each task keeps the A0 scope and uses observable regression behavior.

**Goal:** Complete the owner-specified A0 foundation on `feat/a0-foundation` and stop for owner review.

**Architecture:** Preserve the FastAPI/SQLite backend and vanilla frontend. Vendor the currently used icon and chart libraries at fixed versions, self-host the requested fonts, keep the existing UI structure, replace simulated browser coverage with real local-app/backend Playwright coverage, and extend CI without deployment steps.

**Tech Stack:** Python 3.11/3.12, FastAPI, Pydantic, SQLAlchemy, APScheduler, SQLite, vanilla JavaScript/HTML/CSS, Playwright, GitHub Actions.

**Spec:** Owner-provided A0 spec attached as `Pasted text.txt` in this request.

## Global Constraints

- Implement A0 only; do not begin A1 or the A3 UI redesign.
- Work only on `feat/a0-foundation`, based on `b3e46b8f3f24b67919a396d4b93517fd5dec46b8`.
- Preserve authentication, ownership checks, strict action validation, deletion confirmation, reminder retry behavior, and WebSocket ticket authentication.
- Browser requests may target only parsed hostnames `localhost`, `127.0.0.1`, or `::1`.
- Core dependencies must use exact stable pins compatible with Python 3.11 and 3.12.
- Do not deploy, push, create a PR, or merge.
- Record all evidence under `docs/evidence/a0-foundation/`; do not include secrets or personal data.

## Review Focus

- A missing or failed Lucide initializer must not prevent sign-in or authenticated app setup; pin this with a browser regression that blocks the local icon file.
- Redirected, dynamically loaded, font, image, fetch, and WebSocket requests must be observed and rejected when their parsed hostname is external; pin this with the fail-closed request guard before navigation.
- Chat without an installed model must return a non-empty graceful result through the real app and backend; explicitly report that this is not a real-model test.
- Every remaining visible navigation item must select its working view or action; verify Chat, Tasks, Calendar, Knowledge, Insights, and Settings.
- Removed sidebar entries must leave no mobile overflow, clipping, or invisible keyboard focus at the five required viewport sizes.

---

### Task 1: Record the verified baseline

**Files:**
- Create: `docs/evidence/a0-foundation/baseline/BASELINE.md`
- Create: `docs/evidence/a0-foundation/baseline/` screenshots and browser logs

- [x] Verify exact starting SHA, clean tree, branch availability, architecture, collection count, and pre-change browser behavior.
- [x] Capture normal and CDN-blocked browser evidence before source changes.

### Task 2: Add real browser regressions first

**Files:**
- Modify: `tests/browser/test_frontend_smoke.py`
- Modify: `requirements-browser.txt` only if the browser API needed for WebSocket interception requires a newer fixed Playwright release.

- [x] Add a real backend subprocess fixture with a temporary `DATA_DIR`, local auth secret, and scheduler disabled.
- [x] Add the request guard before navigation; parse URL hostnames, abort external HTTP requests, and route/observe WebSockets before the page is loaded.
- [x] Add real UI checks for account registration/sign-in, Tasks create/complete/persist, no-model Chat, chart rendering, remaining navigation, dead-entry removal, keyboard focus, and the five required viewport sizes.
- [x] Run the new browser tests against the unmodified application and confirm expected failure from external assets and the dead controls. The captured red run is in `baseline/playwright-red-preimplementation.txt`.

### Task 3: Self-host browser dependencies

**Files:**
- Modify: `frontend/index.html`, `frontend/css/styles.css`, and the smallest necessary icon initialization code.
- Create: fixed-version `frontend/vendor/` assets and their license files.
- Create: local Sora, Inter, and JetBrains Mono font subsets/weights plus their OFL files and attribution.

- [x] Vendor Lucide and Chart.js at documented fixed versions; remove remote script URLs and mutable `latest` references.
- [x] Add local `@font-face` sources and remove Google Fonts; keep present typography and layout stable.
- [x] Guard icon initialization so failure cannot abort sign-in; preserve chart rendering and icon behavior.
- [x] Run the browser tests with all non-local hosts blocked and confirm zero attempted external requests.

### Task 4: Remove dead navigation

**Files:**
- Modify: `frontend/index.html` and minimal responsive rules in `frontend/css/styles.css` if measurements require them.

- [x] Remove only Recents, Saved, and Projects; retain the existing visual hierarchy and functional views.
- [x] Run the navigation, viewport, keyboard, and touch-target browser checks.

### Task 5: Upgrade core backend pins with compatibility evidence

**Files:**
- Modify: `requirements.txt` and only manifests needed to keep core, optional AI/RAG, and test dependency sets coherent.
- Modify: backend compatibility code only where a demonstrated test or startup failure requires it.
- Create: `docs/evidence/a0-foundation/DEPENDENCY_DECISIONS.md`.

- [x] Record each previous pin, exact proposal, official source, Python support, relevant breaking changes, and reason before editing pins.
- [x] Upgrade only justified core pins; keep optional inference/RAG dependencies out of the core test install.
- [x] Run test collection, the backend suite, dependency checks, and model-free startup on Python 3.11 and 3.12; run Python 3.12 Windows compatibility checks.
- [x] Confirm existing security tests remain intact and pass.

### Task 6: Extend CI

**Files:**
- Modify: `.github/workflows/ci.yml`.

- [x] Add Linux Python 3.11 and 3.12 core test jobs plus Python 3.12 Windows compatibility.
- [x] Run the real-app Playwright Chromium suite with the strict external request guard and no downloaded model.
- [x] Retain appropriate redacted screenshots/failure artifacts; do not add deployment steps. Hosted CI was not run because the branch was not pushed.

### Task 7: Capture final evidence, report, and commit

**Files:**
- Create: `docs/evidence/a0-foundation/final/` screenshots and browser recording.
- Create/update: `TEST_RESULTS.md`, `NETWORK_AUDIT.md`, `SECURITY_REGRESSION.md`, `ASSET_INVENTORY.md`, `SOURCE_CHANGES.md`, `A0_REPORT.md`.

- [x] Measure real HTML/JS/CSS/font/library payload sizes and responsive geometry before/after.
- [x] Capture screenshots at all required viewports and record a real sign-in, Tasks, Chat, and navigation interaction without exposing credentials.
- [x] Run required final commands, report exact statuses, create a scoped reviewable commit, and stop without push/PR/A1 work.
