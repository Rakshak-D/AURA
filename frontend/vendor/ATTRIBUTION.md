# Bundled browser asset attribution

These assets are served by AURA from `/static/vendor/`; the versioned directory
names and font filenames identify the exact upstream package releases.

| Browser asset | Upstream package | Version | License |
|---|---|---:|---|
| `lucide-1.73.0/lucide.min.js` | [Lucide](https://www.npmjs.com/package/lucide) | 1.73.0 | ISC, included as `licenses/LUCIDE-1.73.0-LICENSE.txt` |
| `chart.js-4.6.1/chart.umd.min.js` | [Chart.js](https://www.npmjs.com/package/chart.js) | 4.6.1 | MIT, included as `licenses/CHART.JS-4.6.1-LICENSE.md` |
| `fonts/sora-latin-wght-normal-5.3.0.woff2` | [Sora Variable](https://www.npmjs.com/package/@fontsource-variable/sora) | 5.3.0 | SIL OFL 1.1, included as `licenses/SORA-5.3.0-OFL.txt` |
| `fonts/inter-latin-wght-normal-5.3.0.woff2` | [Inter Variable](https://www.npmjs.com/package/@fontsource-variable/inter) | 5.3.0 | SIL OFL 1.1, included as `licenses/INTER-5.3.0-OFL.txt` |
| `fonts/jetbrains-mono-latin-wght-normal-5.3.0.woff2` | [JetBrains Mono Variable](https://www.npmjs.com/package/@fontsource-variable/jetbrains-mono) | 5.3.0 | SIL OFL 1.1, included as `licenses/JETBRAINS-MONO-5.3.0-OFL.txt` |

Only the Latin normal variable WOFF2 subset is bundled for each font. Inter is
used by the existing interface. Sora and JetBrains Mono are locally available
for the later design system and are not applied to the current interface.
