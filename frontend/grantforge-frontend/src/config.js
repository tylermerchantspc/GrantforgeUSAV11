// src/config.js — v1.4 (backend v11.1 perfect alignment)

// Ensure no accidental double slashes in API_BASE
function sanitizeBase(url) {
  if (!url) return "";
  return url.endsWith("/") ? url.slice(0, -1) : url;
}

// Main backend URL (Render or Vite env)
export const API_BASE = sanitizeBase(
  import.meta.env.VITE_API_BASE ||
  "https://grantforgeusa-v11-backend.onrender.com"
);

// Stable backend endpoints (never put trailing slashes here)
export const ENDPOINTS = Object.freeze({
  health: `${API_BASE}/get/health`,
  offline: `${API_BASE}/get/offline`,
  debugPaths: `${API_BASE}/get/debug-paths`,

  questionnaire: `${API_BASE}/questionnaire`,
  preview: `${API_BASE}/preview`,
  checkout: `${API_BASE}/create-checkout-session`,
  receipt: `${API_BASE}/receipt`,
  downloadBySession: `${API_BASE}/download-by-session`,
});

export default Object.freeze({ API_BASE, ENDPOINTS });
