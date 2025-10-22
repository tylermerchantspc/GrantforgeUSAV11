// src/App.jsx — vertical, mobile-first intake (inline styles)

import { useState } from "react";
import { API_BASE, ENDPOINTS } from "./config";

// tiny inline style helpers so layout never breaks
const S = {
  page: { maxWidth: 760, margin: "28px auto", padding: "0 16px" },
  card: {
    background: "#fff",
    borderRadius: 14,
    boxShadow: "0 8px 24px rgba(0,0,0,0.08)",
    padding: 24,
  },
  h1: { margin: 0, fontSize: 32, lineHeight: 1.2, color: "#0f172a" },
  sub: { margin: "6px 0 16px 0", color: "#5b7083" },
  label: { display: "block", width: "100%", margin: "12px 0", fontWeight: 600 },
  input: {
    display: "block",
    width: "100%",
    marginTop: 6,
    padding: "12px 12px",
    border: "1px solid #d0d7de",
    borderRadius: 10,
    background: "#fff",
    font: "inherit",
    color: "#0f172a",
  },
  ta: { minHeight: 104, resize: "vertical" },
  btn: {
    width: "100%",
    marginTop: 12,
    border: 0,
    borderRadius: 10,
    padding: "12px 14px",
    fontWeight: 700,
    background: "#1e90ff",
    color: "#fff",
    cursor: "pointer",
  },
  warn: {
    background: "#fff7ed",
    color: "#9a3412",
    border: "1px solid #fed7aa",
    padding: "10px 12px",
    borderRadius: 10,
    marginTop: 8,
  },
  list: { listStyle: "none", padding: 0, margin: "10px 0 0 0" },
  li: {
    margin: "8px 0",
    padding: "10px 12px",
    background: "#f8fafc",
    border: "1px solid #d0d7de",
    borderRadius: 10,
  },
  a: { color: "#0a68d6", fontWeight: 700, textDecoration: "none" },
  meta: { color: "#5b7083", marginTop: 4 },
  price: { marginTop: 10, fontWeight: 700 },
};

export default function App() {
  // intake fields
  const [org, setOrg] = useState("");
  const [who, setWho] = useState("");
  const [kw, setKw] = useState("");
  const [amount, setAmount] = useState("");
  const [budget, setBudget] = useState("");
  const [title, setTitle] = useState("");
  const [timeline, setTimeline] = useState("");
  const [aud, setAud] = useState("");
  const [notes, setNotes] = useState("");

  const [recs, setRecs] = useState([]);
  const [price, setPrice] = useState(null);
  const [status, setStatus] = useState("");

  const CATS = [
    "Teacher (Classroom)",
    "School (Public/Private)",
    "501(c)(3) Nonprofit",
    "Church / Faith-based",
    "Small Business (≤ $500k)",
    "Medium Business ($500k–$2M)",
    "Large Organization ($2M+)",
    "City / Municipality",
  ];

  function computePrice(whoVal, budgetVal) {
    if (whoVal === "Teacher (Classroom)") return 9.99;
    const n = Number(budgetVal || 0);
    if (isNaN(n)) return null;
    if (n <= 500000) return 49.99;
    if (n <= 2000000) return 99.99;
    return 199.99;
  }

  async function handleRecommend(e) {
    e.preventDefault();
    setStatus("Scoring opportunities…");

    // call your backend scoring (you already added grants.json + scoring)
    const body = {
      organization: org,
      who,
      keywords: kw,
      amountRequested: Number(amount || 0),
      annualBudget: Number(budget || 0),
      projectTitle: title,
      timeline,
      audience: aud,
      notes,
    };

    try {
      const r = await fetch(`${API_BASE}/find-grants`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || "Failed");

      // expect j.results = [{title, program_url, deadline, min_amount, max_amount, match_score, requires_match_percent}, ...]
      setRecs(j.results || []);
      setStatus("");
      setPrice(computePrice(who, budget));
      window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
    } catch (err) {
      console.error(err);
      setStatus("Could not fetch recommendations.");
    }
  }

  async function handleCheckout() {
    try {
      setStatus("Creating checkout…");
      const r = await fetch(ENDPOINTS.checkout, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: org || "Client",
          category: who || "General",
          isTeacher: who === "Teacher (Classroom)",
        }),
      });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || "Stripe error");
      // redirect client to Stripe
      window.location.href = j.url;
    } catch (e) {
      console.error(e);
      setStatus("Checkout failed.");
    }
  }

  return (
    <div style={S.page}>
      <div style={S.card}>
        <h1 style={S.h1}>GrantForgeUSA</h1>
        <p style={S.sub}>
          “Unless the Lord builds the house, the builders labor in vain.” — Psalm 127:1
        </p>

        <h3>Tell us about your project (Free Intake)</h3>
        <p className="muted" style={{ marginTop: -6 }}>
          Intake is free. You only pay if you want a full custom draft.
        </p>

        <form onSubmit={handleRecommend}>
          <label style={S.label}>
            Organization
            <input style={S.input} value={org} onChange={e => setOrg(e.target.value)} placeholder="Your Organization" />
          </label>

          <label style={S.label}>
            Who are you?
            <select style={S.input} value={who} onChange={e => setWho(e.target.value)}>
              <option value="">Select a category</option>
              {CATS.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>

          <label style={S.label}>
            Keywords (comma separated)
            <input style={S.input} value={kw} onChange={e => setKw(e.target.value)} placeholder="e.g., STEM, food, youth" />
          </label>

          <label style={S.label}>
            Amount Requested (USD)
            <input style={S.input} type="number" min="0" value={amount} onChange={e => setAmount(e.target.value)} placeholder="e.g., 2500" />
          </label>

          <label style={S.label}>
            Annual Budget (USD)
            <input style={S.input} type="number" min="0" value={budget} onChange={e => setBudget(e.target.value)} placeholder="e.g., 60000" />
          </label>

          <label style={S.label}>
            Project Title
            <input style={S.input} value={title} onChange={e => setTitle(e.target.value)} placeholder="Short name of the project" />
          </label>

          <label style={S.label}>
            Timeline
            <input style={S.input} value={timeline} onChange={e => setTimeline(e.target.value)} placeholder="What do you need & when?" />
          </label>

          <label style={S.label}>
            Audience / Who benefits?
            <input style={S.input} value={aud} onChange={e => setAud(e.target.value)} placeholder="Who is served (students, vets, families)?" />
          </label>

          <label style={S.label}>
            Notes (optional)
            <textarea style={{ ...S.input, ...S.ta }} value={notes} onChange={e => setNotes(e.target.value)} placeholder="Anything else we should know?" />
          </label>

          {status && <div style={S.warn}>{status}</div>}

          <button type="submit" style={S.btn}>See Recommendations</button>
        </form>

        {/* results */}
        {recs.length > 0 && (
          <>
            <h3 style={{ marginTop: 22 }}>Recommended Opportunities</h3>
            <ul style={S.list}>
              {recs.map((g, i) => (
                <li key={i} style={S.li}>
                  <a href={g.program_url} target="_blank" rel="noreferrer" style={S.a}>
                    {g.title}
                  </a>
                  <div style={S.meta}>
                    {g.min_amount ? `$${g.min_amount.toLocaleString()}` : ""}{g.max_amount ? `–$${g.max_amount.toLocaleString()}` : ""}
                    {g.deadline ? ` — Deadline ${g.deadline}` : ""} — Fit {Math.round((g.match_score || 0) * 100)}%
                    {typeof g.requires_match_percent === "number" ? ` — Match Required ${g.requires_match_percent}%` : ""}
                  </div>
                </li>
              ))}
            </ul>

            <div style={S.price}>
              Drafting fee: ${price?.toFixed(2) ?? "—"}
              <div className="muted" style={{ marginTop: 6 }}>
                Short preview is free. You pay only if you want a full custom draft of the opportunity you select.
              </div>
            </div>

            <button onClick={handleCheckout} style={S.btn}>Proceed to Secure Payment</button>
          </>
        )}
      </div>
      <p style={{ textAlign: "center", marginTop: 10, color: "#5b7083" }}>
        © 2025 GrantForgeUSA — Built with faith, for those who build their communities.
      </p>
    </div>
  );
}
