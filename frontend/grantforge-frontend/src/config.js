// src/config.js — v11.2
export const API_BASE = "https://grantforgeusa-v11-backend.onrender.com";

export const ENDPOINTS = {
  health:   `${API_BASE}/get/health`,
  find:     `${API_BASE}/find-grants`,       // primary
  draft:    `${API_BASE}/draft`,             // optional
  checkout: `${API_BASE}/create-checkout-session`,
};

export default { API_BASE, ENDPOINTS };
