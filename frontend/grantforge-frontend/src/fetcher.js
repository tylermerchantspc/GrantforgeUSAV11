// src/fetcher.js — v11 scoring API client
import { API_BASE, ENDPOINTS } from "./config";

export async function apiHealth() {
  const r = await fetch(ENDPOINTS.health, { method: "GET" });
  if (!r.ok) throw new Error("health failed");
  return r.json();
}

export async function getShortlist(input) {
  // input: { organization, category, keywords, amountRequested, budget, timeline, projectTitle, audience, outcomes }
  const r = await fetch(ENDPOINTS.shortlist, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input || {}),
  });
  if (!r.ok) throw new Error("shortlist failed");
  return r.json();
}

export async function getDraft(input) {
  const r = await fetch(ENDPOINTS.draft, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input || {}),
  });
  if (!r.ok) throw new Error("draft failed");
  return r.json();
}
