// src/fetcher.js — v1.2
import { API_BASE, ENDPOINTS } from "./config";

async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return r.json();
}

async function getJSON(url) {
  const r = await fetch(url);
  return r.json();
}

export async function shortlist(payload) {
  // backend supports /questionnaire (and /search as alias)
  return postJSON(ENDPOINTS.questionnaire, payload);
}

export async function getPreview(payload) {
  return postJSON(ENDPOINTS.preview, payload);
}

export async function createCheckoutSession(payload) {
  return postJSON(ENDPOINTS.checkout, payload);
}

export async function receiptBySession(sessionId) {
  return getJSON(`${ENDPOINTS.receipt}?session_id=${encodeURIComponent(sessionId)}`);
}

// Build the success-download URL from a Stripe session id:
export function downloadUrlBySession(sessionId) {
  return `${ENDPOINTS.downloadBySession}?session_id=${encodeURIComponent(sessionId)}`;
}

export async function health() {
  return getJSON(ENDPOINTS.health);
}

export { API_BASE };
