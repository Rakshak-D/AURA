# A0 Changed-File Inventory

## Application and configuration changes

- `.github/workflows/ci.yml` — Linux Python 3.11/3.12 checks, Windows Python 3.12 compatibility, frontend checks, and Playwright browser regressions. The existing localhost container smoke job was retained; no external deployment was performed.
- `backend/app/main.py` — equivalent FastAPI lifespan compatibility for current Starlette and gzip compression scoped to static-file responses; removed remote CDN hosts from CSP.
- `frontend/index.html` — fixed-version local library URLs, dead Recents/Saved/Projects removal, and accessible navigation/menu labels.
- `frontend/css/styles.css` — local font faces, no Google Fonts import, removed dead-entry styles, and responsive mobile navigation/touch target fixes.
- `frontend/js/calendar.js`, `frontend/js/main.js`, `frontend/js/settings.js`, `frontend/js/tasks.js`, `frontend/js/upload.js` — safe icon refresh and unauthenticated initial-load handling so a missing icon or absent sign-in token does not block the application.
- `requirements.txt`, `requirements-dev.txt`, `requirements-browser.txt` — exact Python 3.11/3.12 core, test, and browser dependency pins.
- `tests/browser/test_frontend_smoke.py` — real local backend/browser suite with strict HTTP/WebSocket hostname guards and seven end-to-end cases.
- `tests/test_foundation.py`, `tests/test_frontend_contracts.py` — lifespan/model-free startup and local/versioned browser dependency contract coverage.

## Added runtime assets

- `frontend/vendor/ATTRIBUTION.md`
- `frontend/vendor/chart.js-4.6.1/chart.umd.min.js`
- `frontend/vendor/lucide-1.73.0/lucide.min.js`
- `frontend/vendor/fonts/inter-latin-wght-normal-5.3.0.woff2`
- `frontend/vendor/fonts/jetbrains-mono-latin-wght-normal-5.3.0.woff2`
- `frontend/vendor/fonts/sora-latin-wght-normal-5.3.0.woff2`
- `frontend/vendor/licenses/CHART.JS-4.6.1-LICENSE.md`
- `frontend/vendor/licenses/LUCIDE-1.73.0-LICENSE.txt`
- `frontend/vendor/licenses/INTER-5.3.0-OFL.txt`
- `frontend/vendor/licenses/JETBRAINS-MONO-5.3.0-OFL.txt`
- `frontend/vendor/licenses/SORA-5.3.0-OFL.txt`

## Added A0 evidence and documentation

- `docs/evidence/a0-foundation/IMPLEMENTATION_PLAN.md`
- `docs/evidence/a0-foundation/DEPENDENCY_DECISIONS.md`
- `docs/evidence/a0-foundation/TEST_RESULTS.md`
- `docs/evidence/a0-foundation/NETWORK_AUDIT.md`
- `docs/evidence/a0-foundation/SECURITY_REGRESSION.md`
- `docs/evidence/a0-foundation/ASSET_INVENTORY.md`
- `docs/evidence/a0-foundation/SOURCE_CHANGES.md`
- `docs/evidence/a0-foundation/A0_REPORT.md`
- `docs/evidence/a0-foundation/baseline/` — pre-change screenshots, browser/network logs, and the expected red run against the unmodified app.
- `docs/evidence/a0-foundation/final/` — Python results, browser results, layout/payload measurements, screenshots, and `recordings/a0-user-journey.webm`.

The baseline Playwright CLI snapshots and console log are preserved under `docs/evidence/a0-foundation/baseline/playwright-cli/` as supplemental raw evidence. Browser-generated test identifiers are disposable test data; no credentials or tokens are included.
