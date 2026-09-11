# Changelog

## 2026-09-10 — private human-test release candidate

- Restored the live GrantForgeUSA intake → federal opportunity search → preview → Stripe test-checkout workflow for controlled private testing.
- Replaced applicant-budget pricing tiers with one $49.99 price for a selected customized full proposal draft; search, screening, official links, and preview remain free.
- Expanded grant-writer applicant coverage to K-12 institutions, colleges/universities/research institutions, nonprofits, faith organizations, small businesses, for-profit organizations, local/state/Tribal governments, housing authorities, eligible independent applicants, and other eligible applicants.
- Kept student financial-aid/student-applicant services outside the GrantForgeUSA product while allowing institutions and grant professionals serving students to pursue eligible institutional grants.
- Switched production federal matching to the live Grants.gov API with stable opportunity-ID revalidation before preview and checkout.
- Added conservative applicant-code screening, free-text eligibility restriction checks, applicant-state/geography checks, award floor/ceiling checks, and project-specific relevance gates.
- Treat Grants.gov applicant code 25 (Others) as a recall path only; the notice text must positively support the submitted applicant class before an opportunity can pass.
- Added named-state-list rejection and retained Appalachian Regional Commission geography protection.
- Corrected Grants.gov cost-sharing yes/no parsing and carried the cost-sharing signal into proposal drafting without inventing a match percentage.
- Replaced generic/hardcoded proposal outcomes and unsupported capacity claims with applicant-specific drafting, verification prompts, and notice-controlled language.
- Rebuilt PDF pagination using ReportLab flowables with protected header/footer space; the prior first-page footer collision no longer occurs in QA rendering.
- Strengthened checkout acknowledgment for immediate customized drafting, final-sale terms, nondelivery exception, no funding guarantee, and applicant verification responsibility.
- The private Vercel test host remains no-index. Stripe remains in test mode until the private human-test group approves the release candidate.

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