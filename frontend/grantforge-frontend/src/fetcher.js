// src/fetcher.js — v1.1

import { ENDPOINTS } from "./config";

export async function apiHealth() {
  const r = await fetch(ENDPOINTS.health);
  return r.json();
}

export async function findGrants(intake) {
  const r = await fetch(ENDPOINTS.questionnaire, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(intake),
  });
  return r.json();
}

export async function getPreview(grantId, intake) {
  const r = await fetch(ENDPOINTS.preview, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ grant_id: grantId, intake }),
  });
  return r.json();
}

export async function startCheckout({ grantId, intake, category }) {
  const r = await fetch(ENDPOINTS.checkout, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ grant_id: grantId, intake, category }),
  });
  return r.json();
}

export async function finalizeDraft(sessionId) {
  const url = `${ENDPOINTS.finalize}?session_id=${encodeURIComponent(sessionId)}`;
  const r = await fetch(url);
  return r.json();
}
