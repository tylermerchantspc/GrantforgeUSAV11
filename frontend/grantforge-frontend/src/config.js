// src/config.js — GrantforgeUSA v1.1
// Central config for API base + endpoints

export const API_BASE =
  import.meta.env.VITE_API_BASE || "https://grantforgeusa-v11-backend.onrender.com";

export const ENDPOINTS = {
  health: `${API_BASE}/get/health`,
  shortlist: `${API_BASE}/questionnaire`,
  draft: `${API_BASE}/draft`,
  checkout: `${API_BASE}/create-checkout-session`,
};

export default { API_BASE, ENDPOINTS };
