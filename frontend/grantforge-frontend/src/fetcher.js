// src/fetcher.js — v1.3.1 (production locked, backend v11 aligned)
import { ENDPOINTS, API_BASE } from "./config";

/* ---------- safe fetch helper with timeout & clearer errors ---------- */
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
    return await res.json();
  } catch (err) {
    return { ok: false, error: err.message || String(err) };
  } finally {
    clearTimeout(id);
  }
}

/* ---------- API wrappers ---------- */
export async function shortlist(payload) {
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

/* ---------- Backend diagnostics (optional) ---------- */
export async function debugPaths() {
  try {
    const res = await fetch(ENDPOINTS.debugPaths, { method: "GET" });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

Object.freeze(ENDPOINTS);
export { API_BASE };
