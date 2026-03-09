# Changelog

## 2026-03-09
- Removed residual intake and payload support for phone/state fields to enforce simplified production intake.
- Strengthened search quality by improving tokenization and enforcing shortlist filtering to grants with maximum awards under $2M.
- Updated narrative generation section naming and polished language consistency for production-ready proposals.
- Updated PDF rendering to include a blue clickable official Grants.gov opportunity hyperlink in "Grant opportunity details".
- Enforced paid-only download flow with tokenized access and additional route rate limits.
- Disabled debug route output by default behind `ENABLE_DEBUG_ENDPOINTS`.
- Added payload sanitization, CSV-safe logging, and log retention pruning.
- Refreshed frontend messaging/CTA copy and modernized styling.
- Added backend test suite (including 10-client simulation coverage) and frontend integration smoke tests.
