// src/config.js — v1.3.1 (production locked, backend v11 aligned)

// Main backend base URL (defaults to Render deployment if env var not set)
export const API_BASE =
  import.meta.env.VITE_API_BASE ||
  "https://grantforgeusa-v11-backend.onrender.com";

// All backend endpoints (stable routes; used across fetcher.js & App.jsx)
export const ENDPOINTS = {
  health: `${API_BASE}/get/health`,
  offline: `${API_BASE}/get/offline`,          // Backend connection check
  debugPaths: `${API_BASE}/get/debug-paths`,  // Diagnostics endpoint
  questionnaire: `${API_BASE}/questionnaire`,
  preview: `${API_BASE}/preview`,
  checkout: `${API_BASE}/create-checkout-session`,
  receipt: `${API_BASE}/receipt`,
  downloadBySession: `${API_BASE}/download-by-session`,
};

// Export both object and default
export default Object.freeze({ API_BASE, ENDPOINTS });
