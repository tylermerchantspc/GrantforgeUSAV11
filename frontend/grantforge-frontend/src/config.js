// src/config.js — v1.4 (backend v11.2 aligned)
function sanitizeBase(url) {
  if (!url) return "";
  return url.endsWith("/") ? url.slice(0, -1) : url;
}

export const API_BASE = sanitizeBase(
  import.meta.env.VITE_API_BASE ||
  "https://grantforgeusa-v11-backend.onrender.com"
);

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

export default Object.freeze({ API_BASE, ENDPOINTS });
