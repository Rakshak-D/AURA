# A0 Local Browser Asset Inventory

All runtime browser assets are served from AURA's own origin at fixed versioned paths. The vendored tree contains 11 files totaling 838,654 bytes, including runtime files, license texts, and attribution. Runtime assets alone total 819,565 bytes.

| Asset | Version / license | File | Bytes | SHA-256 |
|---|---|---|---:|---|
| Lucide | 1.73.0 / ISC | `frontend/vendor/lucide-1.73.0/lucide.min.js` | 487,171 | `ED271FFBE31F0905AF8A6EF7B45A70831A517A70909795E637135E218A543C5E` |
| Chart.js | 4.6.1 / MIT | `frontend/vendor/chart.js-4.6.1/chart.umd.min.js` | 210,082 | `87364CC2B2A76A6684929E7D6B80B18A897794DB38400CAFF1FCF1791C6925D2` |
| Inter | 5.3.0 / OFL 1.1 | `frontend/vendor/fonts/inter-latin-wght-normal-5.3.0.woff2` | 48,256 | `3100E775E8616CD2611BEECFA23A4263D7037586789B43F035236A2E6FBD4C62` |
| JetBrains Mono | 5.3.0 / OFL 1.1 | `frontend/vendor/fonts/jetbrains-mono-latin-wght-normal-5.3.0.woff2` | 40,404 | `18BE452724BFDC236C074CA94A249A7F41A86752C7D04AB258CE9ED5651F6A7E` |
| Sora | 5.3.0 / OFL 1.1 | `frontend/vendor/fonts/sora-latin-wght-normal-5.3.0.woff2` | 33,652 | `FA26406EEDA9A3C6EC3D9EA8813C3045D6DC755E30C716D5C094E8EF43BE5A7F` |

Full licenses are in `frontend/vendor/licenses/`; package sources and attribution are in `frontend/vendor/ATTRIBUTION.md`. The app currently loads Inter only; Sora and JetBrains Mono are included for the future design system without applying a typography redesign in A0.

## Initial page payload

Measured by Chromium DevTools Protocol `Network.loadingFinished.encodedDataLength` with browser cache disabled. The final load used 15 local resources: HTML, CSS, ten app JavaScript files, Chart.js, Lucide, and Inter. Sora and JetBrains Mono are packaged but are not downloaded by the current page.

| Initial static payload | Body bytes | Transfer bytes |
|---|---:|---:|
| Baseline | 802,433 | 300,556 |
| Final | 861,404 | 284,966 |
| Change | +58,971 | -15,590 (-5.2%) |

The final body total includes the self-hosted Inter file and versioned local libraries. Static responses are gzip-compressed by the local server; the transfer value is the observed browser measurement. Detailed final resource sizes are in `final/payload-measurements.json`; baseline breakdown is in `baseline/BASELINE.md`.
