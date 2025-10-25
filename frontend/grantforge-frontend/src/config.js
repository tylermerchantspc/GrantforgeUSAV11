// src/config.js — v1.1
export const API_BASE =
  import.meta.env.VITE_API_BASE || "https://grantforgeusa-v11-backend.onrender.com";

export const ENDPOINTS = {
  health: `${API_BASE}/get/health`,
  questionnaire: `${API_BASE}/questionnaire`,
  preview: `${API_BASE}/preview`,
  checkout: `${API_BASE}/create-checkout-session`,
  finalize: `${API_BASE}/finalize`,
};

export default { API_BASE, ENDPOINTS };
