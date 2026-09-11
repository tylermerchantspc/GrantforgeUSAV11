# GrantForgeUSA

## Current status: controlled founding-pilot soft launch

The September 2026 launch candidate is a **static-first public preview** for a limited founding pilot. It is deliberately separated from the legacy automated checkout flow.

The soft-launch site:

- accepts applications for a 3–5 organization pilot cohort;
- uses one $49.99 flat price for a selected full customized proposal draft;
- does not collect payment or create orders;
- does not expose the legacy local grant dataset as verified opportunity data;
- prepares an application in the visitor's email client instead of storing form data;
- includes privacy, pilot-terms, and service-disclaimer pages;
- is marked `noindex` while the workflow is validated.

## Run the soft-launch frontend

```bash
cd frontend/grantforge-frontend
npm ci
npm run dev
```

Optional environment variable:

```bash
VITE_PILOT_EMAIL=your-pilot-inbox@example.com
```

Build and test:

```bash
npm run lint
npm run test:integration
npm run build
```

## Legacy backend status

`backend/v11_server.py` remains in the repository for controlled development and regression testing. It is **not approved for public paid traffic** in the founding-pilot launch candidate.

Before the legacy flow, or a replacement production service, is enabled, the project must complete the gates in [`docs/FULL_SERVICE_GATES.md`](docs/FULL_SERVICE_GATES.md). In particular:

- opportunity data must come from a current official source and retain verification evidence;
- application, order, payment, draft, token, and download state must use durable storage rather than process memory or ephemeral files;
- payment and payout configuration must be verified end to end;
- privacy, engagement, refund, and disclosure language must receive final review;
- production monitoring, recovery, and support procedures must be tested.

The current `backend/data/grants.json` file is development/demo material and must not be represented as a verified live opportunity inventory.

## Pricing model

| Service | Price |
|---|---:|
| Federal opportunity search, screening, official links, and preview | Free |
| One selected customized full proposal draft | $49.99 |

Final scope is confirmed before an engagement begins. Multiple opportunities, extensive attachments, unusual compliance requirements, or materially incomplete intake may require a separate scope.

## Operating standard

GrantForgeUSA is an independent private service. Pilot work may use proprietary drafting software and automated tools for research organization, drafting, editing, and quality checks, followed by human review. The official funding notice controls. The applicant remains responsible for factual verification, registrations, attachments, certifications, signatures, deadlines, and final submission. Funding is never guaranteed.

Operational references:

- [`docs/SOFT_LAUNCH_RUNBOOK.md`](docs/SOFT_LAUNCH_RUNBOOK.md) — controlled founding-pilot procedure;
- [`docs/FULL_SERVICE_GATES.md`](docs/FULL_SERVICE_GATES.md) — mandatory go/no-go requirements;
- [`docs/OPENAI_PRODUCTION_PLAN.md`](docs/OPENAI_PRODUCTION_PLAN.md) — current Responses API, model-routing, data-control, evaluation, and Codex implementation plan.
