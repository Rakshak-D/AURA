# A0 Browser Network Audit

## Baseline

The original page attempted four external URL loads across three hostnames: `unpkg.com` for mutable `lucide@latest` and its redirect to Lucide 1.73.0, `cdn.jsdelivr.net` for Chart.js, and `fonts.googleapis.com` for Inter. The Google Fonts stylesheet was blocked by the baseline CSP and transferred zero bytes. With all non-local hosts blocked, Lucide failed, its two initializers raised `ReferenceError: lucide is not defined`, and the sign-in panel did not render. See `baseline/external-requests.txt`, `baseline/blocked-external-requests.txt`, `baseline/blocked-browser-console.txt`, and `baseline/cdn-blocked-signin-1440x900.png`.

## Final browser run

**Status: `PASS_REAL`.** The seven final Playwright tests each installed HTTP and WebSocket request guards before page navigation. The guards parse the hostname and allow only `localhost`, `127.0.0.1`, and `::1`; attempted external requests are blocked and recorded. The last seven entries in `final/browser-run-summary.jsonl` show `external_attempts: []` for every test. Each entry also reports no unauthenticated data requests and no uncaught JavaScript errors.

The deliberate missing-icon regression blocks a local Lucide resource to prove sign-in remains usable. Chromium reports one expected `ERR_BLOCKED_BY_CLIENT` console message for that local resource; the other six tests report no console errors. No public host was requested in any final test.

The request guard covers the browser resource and API paths used by the tests, including HTTP requests and WebSockets. This result is evidence for the exercised A0 application; it does not claim that future external integrations work offline.
