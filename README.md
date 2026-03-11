# GrantForgeUSA v11

## Production hardening updates
- Flat pricing is fixed at **$2,500** per grant draft in backend checkout and frontend CTAs.
- Intake excludes phone/state/territory fields.
- Grant PDF includes a clickable Grants.gov opportunity link in the **Grant opportunity details** section.
- Downloads are gated by paid Stripe sessions and one-time download tokens.
- Input sanitization strips tags/control characters and CSV log writing includes formula-injection escaping.
- Debug route `/get/debug-paths` is disabled unless `ENABLE_DEBUG_ENDPOINTS=true`.
- Basic rate limiting is enabled for shortlist, preview, checkout, token creation, and download routes.
- Security headers (HSTS on HTTPS, frame/content-type/referrer policies) are applied to responses.

## Environment variables
Set these for production:
- `STRIPE_SECRET_KEY`
- `STRIPE_PUBLISHABLE_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `FRONTEND_URL`
- `FRONTEND_THANKS_URL`
- `CORS_ORIGINS`
- `ENABLE_DEBUG_ENDPOINTS=false`
- `LOG_RETENTION_DAYS=30`

## Run backend
```bash
pip install -r backend/requirements.txt
python backend/v11_server.py
```

## Run frontend
```bash
cd frontend/grantforge-frontend
npm install
npm run dev
```

## Tests
```bash
pytest backend/tests/test_v11_server.py
cd frontend/grantforge-frontend && npm run test:integration
```

## Monthly Grants Dataset Refresh
Use the CSV loader to refresh `backend/data/grants.json` from the latest Grants.gov export:

```bash
python backend/scripts/update_grants.py --csv /path/to/new/grants-search-YYYYMMDD.csv
```

Optional output override:

```bash
python backend/scripts/update_grants.py --csv /path/to/new/grants-search-YYYYMMDD.csv --out backend/data/grants.json
```
