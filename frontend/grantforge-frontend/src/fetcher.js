// src/fetcher.js — v1.3 (final, backend v11 aligned)
import { ENDPOINTS, API_BASE } from "./config";

/* ---------- small fetch helper with timeout & clearer errors ---------- */
async function safeFetch(url, options = {}, { timeoutMs = 20000 } = {}) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(
        `HTTP ${res.status} ${res.statusText}${
          text ? ` — ${text.slice(0, 200)}` : ""
        }`
      );
    }
    return res.json();
  } finally {
    clearTimeout(id);
  }
}

/* ---------- API wrappers ---------- */
export async function shortlist(payload) {
  // Hide expired by default unless caller explicitly opts in
  const body = JSON.stringify({ includeExpired: false, ...(payload || {}) });
  return safeFetch(ENDPOINTS.questionnaire, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}

export async function getPreview(payload) {
  const body = JSON.stringify(payload || {});
  return safeFetch(ENDPOINTS.preview, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}

export async function createCheckoutSession(payload) {
  const body = JSON.stringify(payload || {});
  return safeFetch(ENDPOINTS.checkout, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}

export async function receiptBySession(sessionId) {
  const u = `${ENDPOINTS.receipt}?session_id=${encodeURIComponent(sessionId)}`;
  return safeFetch(u, { method: "GET" });
}

export function downloadUrlBySession(sessionId) {
  return `${ENDPOINTS.downloadBySession}?session_id=${encodeURIComponent(sessionId)}`;
}

/* ---------- NEW: backend diagnostics ---------- */
export async function debugPaths() {
  try {
    const res = await fetch(ENDPOINTS.debugPaths, { method: "GET" });
    return res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export { API_BASE };
