// src/config.js — v1.2
export const API_BASE =
  import.meta.env.VITE_API_BASE || "https://grantforgeusa-v11-backend.onrender.com";

export const ENDPOINTS = {
  health: `${API_BASE}/get/health`,
  questionnaire: `${API_BASE}/questionnaire`,          // backend alias /search also available
  preview: `${API_BASE}/preview`,
  checkout: `${API_BASE}/create-checkout-session`,
  receipt: `${API_BASE}/receipt`,                      // NEW
  downloadBySession: `${API_BASE}/download-by-session` // NEW
};

export default { API_BASE, ENDPOINTS };
