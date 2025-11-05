// src/fetcher.js — v1.2
import { ENDPOINTS, API_BASE } from "./config";

export async function shortlist(payload) {
  const r = await fetch(ENDPOINTS.questionnaire, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return r.json();
}

export async function getPreview(payload) {
  const r = await fetch(ENDPOINTS.preview, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return r.json();
}

export async function createCheckoutSession(payload) {
  const r = await fetch(ENDPOINTS.checkout, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return r.json();
}

export async function receiptBySession(sessionId) {
  const r = await fetch(`${ENDPOINTS.receipt}?session_id=${encodeURIComponent(sessionId)}`);
  return r.json();
}

export function downloadUrlBySession(sessionId) {
  return `${ENDPOINTS.downloadBySession}?session_id=${encodeURIComponent(sessionId)}`;
}

export { API_BASE };
