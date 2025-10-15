// src/fetcher.js — v1.1
import { ENDPOINTS } from "./config";

export async function apiHealth() {
  const r = await fetch(ENDPOINTS.health);
  if (!r.ok) throw new Error(`Health ${r.status}`);
  return r.json();
}

export async function findGrants(org, keywords) {
  const r = await fetch(ENDPOINTS.shortlist, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ organization: org, keywords })
  });
  if (!r.ok) throw new Error(`Shortlist ${r.status}`);
  return r.json();
}

export async function getDraft(org, topic) {
  const r = await fetch(ENDPOINTS.draft, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ organization: org, topic })
  });
  if (!r.ok) throw new Error(`Draft ${r.status}`);
  return r.json();
}
