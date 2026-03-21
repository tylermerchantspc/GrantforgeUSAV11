// src/config.js — runtime-configured backend endpoints
function sanitizeBase(url) {
  if (!url) return "";
  return url.endsWith("/") ? url.slice(0, -1) : url;
}

export const API_BASE = sanitizeBase(import.meta.env.VITE_API_BASE || "");

export function validateApiBase() {
  if (!API_BASE) {
    throw new Error(
      "Frontend is not configured: missing VITE_API_BASE. Set VITE_API_BASE in your environment and restart the frontend."
    );
  }
}

export const ENDPOINTS = Object.freeze({
  health: `${API_BASE}/get/health`,
  offline: `${API_BASE}/get/offline`,
  questionnaire: `${API_BASE}/questionnaire`,
  preview: `${API_BASE}/preview`,
  checkout: `${API_BASE}/create-checkout-session`,
  createDownloadToken: `${API_BASE}/create-download-token`,
  receipt: `${API_BASE}/receipt`,
  downloadBySession: `${API_BASE}/download-by-session`,
});

export default Object.freeze({ API_BASE, ENDPOINTS, validateApiBase });
