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
Copy `.env.example` and set values through runtime environment variables only (never commit `.env` files).

Required in production:
- `STRIPE_SECRET_KEY`
- `STRIPE_PUBLISHABLE_KEY`
- `FRONTEND_URL`
- `FRONTEND_THANKS_URL`
- `VITE_API_BASE` (frontend runtime)

Optional but recommended:
- `STRIPE_WEBHOOK_SECRET`
- `CORS_ORIGINS`
- `ENABLE_DEBUG_ENDPOINTS=false`
- `LOG_RETENTION_DAYS=30`
- `DOWNLOAD_TOKEN_TTL_SECONDS=86400`

Google/Gemini key contract:
- Use **only** `GOOGLE_API_KEY`.
- `GEMINI_API_KEY` is deprecated and rejected.
- Restrict the key to the required Google Generative Language APIs, with IP/referrer restrictions where possible.

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


## Security incident response checklist (maintainer)
1. Rotate compromised keys in provider consoles immediately (Stripe + Google if exposed).
2. Remove leaked values from git history if a secret ever appeared in prior commits.
3. Example history rewrite (run from a protected maintenance clone):
```bash
git filter-repo --path backend/.env --path frontend/grantforge-frontend/.env --invert-paths
```
4. Force-push rewritten branches and coordinate downstream re-clones.
