// src/fetcher.js — v1.4 (backend v11.1 aligned, production safe)
import { ENDPOINTS, API_BASE } from "./config";

/* ---------- safe fetch helper with timeout & clearer errors ---------- */
async function safeFetch(url, options = {}, { timeoutMs = 20000 } = {}) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    const contentType = res.headers.get("content-type") || "";

    // Try to parse JSON if possible
    const parseJson = async () => {
      try {
        return await res.json();
      } catch {
        return null;
      }
    };

    if (!res.ok) {
      const maybeJson = await parseJson();
      if (maybeJson && typeof maybeJson === "object") {
        // Backend uses { ok: false, error: "..." } on failures
        if (maybeJson.error) {
          throw new Error(maybeJson.error);
        }
      }
      const text = !maybeJson ? await res.text().catch(() => "") : "";
      throw new Error(
        `HTTP ${res.status} ${res.statusText}${
          text ? ` — ${text.slice(0, 200)}` : ""
        }`
      );
    }

    if (contentType.includes("application/json")) {
      const data = await parseJson();
      return data ?? { ok: false, error: "Empty JSON response" };
    }

    // Fallback: non-JSON but ok
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message || String(err) };
  } finally {
    clearTimeout(id);
  }
}

/* ---------- API wrappers ---------- */

export async function shortlist(payload) {
  // includeExpired forced false from frontend for now
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

export async function createDownloadToken(sessionId) {
  return safeFetch(ENDPOINTS.createDownloadToken, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export async function receiptByToken(token) {
  const u = `${ENDPOINTS.receipt}?token=${encodeURIComponent(token)}`;
  return safeFetch(u, { method: "GET" });
}

export function downloadUrlByToken(token) {
  return `${ENDPOINTS.downloadBySession}?token=${encodeURIComponent(token)}`;
}


/* ---------- Health check helper (optional UI) ---------- */

export async function getHealth() {
  try {
    const res = await fetch(ENDPOINTS.health, { method: "GET" });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

Object.freeze(ENDPOINTS);
export { API_BASE };
