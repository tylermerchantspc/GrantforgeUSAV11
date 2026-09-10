# Full-Service Launch Gates

The founding-pilot preview may be shared publicly while these gates remain open because the preview does not take payment, promise automated matching, or represent development data as verified live opportunities. Full paid service must not begin until every critical gate is closed.

## Gate 1 — Verified opportunity data

- Use a current official federal opportunity source.
- Store source URL, opportunity identifier, retrieval time, status, close date, applicant types, award range, cost share, and amendment state.
- Reject closed, archived, forecasted-as-open, or unverifiable records by default.
- Add automated freshness checks and an operator review step.
- Preserve evidence showing which notice version controlled each delivered draft.

**Exit test:** Ten diverse test intakes produce only current, traceable opportunities, and an operator can reproduce every displayed fact from the official notice.

## Gate 2 — Production drafting architecture

- Define the approved model or provider and production billing arrangement.
- Use structured prompts and outputs tied to a requirements matrix.
- Separate applicant facts, official-source facts, assumptions, and generated suggestions.
- Add factuality, completeness, consistency, and unsupported-claim checks.
- Add safe failure behavior when data or drafting services are unavailable.

**Exit test:** A blind review set demonstrates that missing facts are flagged rather than invented, and every core notice requirement is mapped or explicitly marked unresolved.

## Gate 3 — Durable application and order state

- Replace process-memory tokens, checkout references, draft state, and download state with a durable database.
- Replace ephemeral PDF and CSV storage with private durable object storage.
- Encrypt data in transit and at rest.
- Implement retention, deletion, backup, restore, and incident-response procedures.
- Avoid brittle identity controls such as binding an order solely to a changing IP address.

**Exit test:** Restarting or redeploying every service during an active test order does not lose the application, payment state, draft, receipt, or authorized download access.

## Gate 4 — Payment and payout readiness

- Verify the merchant account, business identity, business address, settlement account, live keys, webhook secret, statement descriptor, taxes, receipts, dispute handling, and payout path.
- Use idempotent fulfillment and record validated webhook events.
- Test successful payment, failed payment, cancellation, duplicate webhook, refund or credit decision, dispute, and payout reconciliation.
- Display price, scope, refund terms, and support contact before purchase.

**Exit test:** A low-value live transaction completes from checkout through payout and reconciliation without manual reconstruction or exposed secrets.

## Gate 5 — Security and reliability

- Remove tracked virtual environments, caches, generated files, and any historical secrets from repository history as required.
- Add continuous integration, dependency scanning, secret scanning, and protected-branch review.
- Lock production CORS, security headers, rate limiting, authentication, authorization, and administrative access.
- Add structured logs, uptime monitoring, error alerting, abuse controls, and recovery procedures.
- Conduct a privacy and threat-model review of the complete data flow.

**Exit test:** The production threat model, recovery test, access review, and automated security checks pass with no unresolved critical finding.

## Gate 6 — Legal, privacy, and brand readiness

- Confirm the business name and public branding through appropriate legal clearance.
- Obtain final review of engagement terms, privacy notice, refund and cancellation policy, limitation language, software disclosure, and applicant responsibilities.
- Replace outdated or inconsistent NDAs and entity descriptions.
- Define handling rules for education records, health information, confidential business data, and government-controlled information before accepting such material.
- Ensure marketing claims match demonstrated capabilities and turnaround data.

**Exit test:** Approved public terms and operating policies match the actual product, vendors, data flow, and fulfillment process.

## Gate 7 — Pilot evidence and operating capacity

- Complete the 3–5 organization pilot without a critical data, security, payment, or compliance incident.
- Measure turnaround, corrections, missed requirements, revision load, support volume, and applicant feedback.
- Establish daily capacity, service-level targets, escalation ownership, and a pause mechanism.
- Document the manual fallback for provider, data-source, and hosting outages.

**Exit test:** Pilot evidence supports the public claims, workload is sustainable, and intake can be paused without losing active work.

## Launch decision

A full-service launch requires a signed internal go or no-go record showing the evidence for each exit test, remaining noncritical risks, responsible owner, and rollback plan.
