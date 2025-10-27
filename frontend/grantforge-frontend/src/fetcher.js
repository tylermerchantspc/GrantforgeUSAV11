// src/fetcher.js
import { API_BASE } from "./config";

export async function shortlist(payload) {
  const r = await fetch(`${API_BASE}/questionnaire`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return r.json();
}

export async function getPreview(payload) {
  const r = await fetch(`${API_BASE}/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return r.json();
}

export async function createCheckoutSession(payload) {
  const r = await fetch(`${API_BASE}/create-checkout-session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return r.json();
}

// Build the success-download URL from a Stripe session id:
export function downloadUrlBySession(sessionId) {
  return `${API_BASE}/download-by-session?session_id=${encodeURIComponent(sessionId)}`;
}
