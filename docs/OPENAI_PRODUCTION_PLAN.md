# GrantForgeUSA OpenAI Production Plan

**Architecture date:** September 10, 2026  
**Applies to:** full-service build after the founding-pilot preview

The public soft launch is intentionally static-first. It does not depend on a model, a grant-search backend, or online checkout. This plan defines the next production architecture using OpenAI for drafting and review while keeping official federal data—not model output—as the factual source of truth.

## 1. Source-of-truth boundary

Opportunity discovery must use the official Grants.gov REST API:

- `POST /v1/api/search2` for candidate discovery;
- `POST /v1/api/fetchOpportunity` for the current opportunity record and details;
- `oppStatus=posted` as the default public eligibility filter;
- a stored verification timestamp, official identifier, source URL, status, close date, award range, applicant categories, cost-share terms, and amendment/version evidence for every accepted engagement.

Model web search may assist research, but it must never replace or silently override the current official notice. Forecasted, closed, archived, incomplete, or unverifiable opportunities fail closed.

## 2. OpenAI model layer

Build new model integrations on the OpenAI Responses API rather than the deprecated Assistants API.

Recommended staged routing:

1. **Normalization and extraction:** a cost-balanced current model, initially `gpt-5.6-terra`, converts official opportunity data and applicant intake into a strict internal schema.
2. **Draft production:** the same model may create the first narrative draft when the requirements matrix is complete.
3. **Compliance and quality review:** `gpt-5.6-sol` performs the higher-reasoning final review against the official notice, requirements matrix, applicant facts, and prohibited-invention rules.
4. **GPT-6 Astra evaluation:** test `gpt-6-astra` behind a feature flag only after API access is confirmed and it passes the GrantForgeUSA evaluation set. Do not make a newly released or limited-rollout model a hard production dependency.

Model identifiers must be configuration values, not scattered constants. The service must preserve the model name, prompt/version identifier, reasoning setting, and request identifier for each production artifact.

## 3. Structured workflow

Every engagement moves through explicit durable states:

`received -> screened -> opportunity_verified -> intake_complete -> drafting -> human_review -> delivered -> revision -> closed`

Each model stage returns a strict structured object. At minimum, keep separate fields for:

- official-source facts;
- applicant-supplied facts;
- unresolved questions;
- assumptions requiring approval;
- proposed narrative language;
- requirements-matrix coverage;
- citations or source pointers;
- quality-control findings.

Generated language must not be allowed to create organization history, partners, statistics, budgets, outcomes, certifications, registrations, demographic facts, or commitments that are absent from approved source material.

## 4. Data controls

- Keep OpenAI credentials server-side in an approved secret manager.
- Default production Responses API calls to `store: false` unless a documented operating need and privacy review justify storage.
- Do not use background mode for sensitive applicant work until its retention characteristics are accepted in the written data policy.
- Do not send Social Security numbers, payment credentials, passwords, protected health information, student education records, export-controlled information, or government-controlled information to the drafting workflow.
- Maintain a vendor/data-flow register and a deletion procedure that covers the database, object storage, logs, email, and model-provider state.

## 5. Required infrastructure

The production service needs:

- durable relational storage for applicants, opportunities, engagements, versions, payments, and audit events;
- private object storage for source notices and delivered files;
- a queue or durable job system for drafting work;
- idempotent payment and fulfillment handlers;
- role-based administrative access;
- structured logs, uptime checks, error alerts, backup/restore testing, and an intake pause switch.

Vercel may continue hosting the frontend. The backend may use a platform suited to durable workers and long-running jobs; it must not depend on process memory or an ephemeral filesystem for business records.

## 6. Evaluation gate

Create a private evaluation set from at least 30 representative cases covering teachers, nonprofits, churches, schools, small businesses, and local governments. Include difficult cases with:

- expired or forecasted opportunities;
- ineligible applicants;
- conflicting dates or award ranges;
- mandatory cost share;
- missing attachments;
- incomplete applicant facts;
- multiple amendments;
- deceptive prompt content inside uploaded documents.

Score at minimum:

- official-fact accuracy;
- eligibility classification;
- requirement coverage;
- unsupported-claim rate;
- consistency among narrative, outcomes, timeline, and budget;
- correct escalation to human review;
- latency and cost per accepted engagement.

No model or prompt version reaches production until it meets the approved thresholds and performs no worse than the current production version on critical safety checks.

## 7. Codex implementation sequence

Use one reviewable pull request per boundary:

1. Grants.gov API client, schemas, fixtures, and freshness tests.
2. Durable opportunity store and verification record.
3. Applicant intake schema, consent, retention, and administrative screening.
4. OpenAI Responses API adapter with structured outputs and provider abstraction.
5. Requirements-matrix generator and unsupported-fact controls.
6. Draft generator and human-review workspace.
7. Evaluation suite and release thresholds.
8. Durable delivery/versioning.
9. Payment, refunds, reconciliation, and payout verification.
10. Production monitoring, recovery drill, legal review, and go/no-go record.

Each pull request must include tests, migration or rollback notes, and evidence that it does not weaken the static soft-launch safety boundary.

## 8. Immediate decision

For the founding pilot, perform official-source verification and human review manually under the runbook. Use the pilot to collect corrected facts, failure cases, turnaround measurements, and reviewer feedback. Those records become the initial evaluation set before automated full-service traffic is enabled.
