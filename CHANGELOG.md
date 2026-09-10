# Changelog

## 2026-09-10 — founding-pilot soft launch

- Replaced the public launch candidate with a static-first founding-pilot site for a 3–5 organization cohort.
- Disabled public checkout and removed the frontend dependency on the legacy backend.
- Restored the approved pricing model: $9.99, $49.99, $99.99, and $199.99.
- Added a local email and clipboard application workflow instead of storing applicant data.
- Added official-source, human-review, no-guarantee, applicant-responsibility, and government-nonaffiliation disclosures.
- Added privacy, pilot-terms, disclaimer, and paused-checkout routes.
- Added no-index controls and restrictive Vercel security headers for the controlled preview.
- Replaced legacy checkout tests with launch-safeguard tests.
- Added GitHub Actions CI, a soft-launch operating runbook, and documented full-service launch gates.

## 2026-03-09

- Removed residual intake and payload support for phone/state fields to enforce simplified production intake.
- Strengthened search quality by improving tokenization and enforcing shortlist filtering to grants with maximum awards under $2M.
- Updated narrative generation section naming and polished language consistency for production-ready proposals.
- Updated PDF rendering to include a clickable official Grants.gov opportunity link.
- Enforced paid-only download flow with tokenized access and additional route rate limits.
- Disabled debug route output by default behind `ENABLE_DEBUG_ENDPOINTS`.
- Added payload sanitization, CSV-safe logging, and log retention pruning.
- Refreshed frontend messaging and styling.
- Added backend and frontend test coverage.
