// src/config.js — v1.3 (final, backend-aligned)
export const API_BASE =
  import.meta.env.VITE_API_BASE ||
  "https://grantforgeusa-v11-backend.onrender.com";

export const ENDPOINTS = {
  health: `${API_BASE}/get/health`,
  offline: `${API_BASE}/get/offline`,          // NEW optional backend check
  debugPaths: `${API_BASE}/get/debug-paths`,  // NEW diagnostics endpoint
  questionnaire: `${API_BASE}/questionnaire`,
  preview: `${API_BASE}/preview`,
  checkout: `${API_BASE}/create-checkout-session`,
  receipt: `${API_BASE}/receipt`,
  downloadBySession: `${API_BASE}/download-by-session`,
};

export default { API_BASE, ENDPOINTS };
