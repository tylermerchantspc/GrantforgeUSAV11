// src/App.jsx — v11.2 vertical flow + footer AI disclosure
import { useState } from "react";
import { ENDPOINTS } from "./config";

const S = {
  page: { maxWidth: 760, margin: "28px auto", padding: "0 16px" },
  card: { background: "#fff", borderRadius: 14, boxShadow: "0 8px 24px rgba(0,0,0,0.08)", padding: 24 },
  h1: { margin: 0, fontSize: 32, lineHeight: 1.2, color: "#0f172a" },
  verse: { margin: "6px 0 16px 0", color: "#5b7083" },
  label: { display: "block", width: "100%", margin: "12px 0", fontWeight: 600 },
  input: { display: "block", width: "100%", marginTop: 6, padding: "12px", border: "1px solid #d0d7de", borderRadius: 10 },
  ta: { minHeight: 104, resize: "vertical" },
  btn: { width: "100%", marginTop: 12, border: 0, borderRadius: 10, padding: "12px 14px", fontWeight: 700, background: "#1e90ff", color: "#fff", cursor: "pointer" },
  warn: { background: "#fff7ed", color: "#9a3412", border: "1px solid #fed7aa", padding: "10px 12px", borderRadius: 10, marginTop: 8 },
  list: { listStyle: "none", padding: 0, margin: "10px 0 0 0" },
  li: { margin: "8px 0", padding: "10px 12px", background: "#f8fafc", border: "1px solid #d0d7de", borderRadius: 10 },
  a: { color: "#0a68d6", fontWeight: 700, textDecoration: "none" },
  meta: { color: "#5b7083", marginTop: 4 },
  footer: { textAlign: "center", marginTop: 16, color: "#5b7083" },
};

const CATS = [
  "Teacher (Classroom)",
  "School (Public/Private)",
  "501(c)(3) Nonprofit",
  "Church / Faith-based",
  "Small Business (≤ $500k)",
  "Medium Business ($500k–$2M)",
  "Large Organization ($2M+)",
  "City / Municipality",
  "Community Club / Civic Group",
];

export default function App() {
  const [org, setOrg] = useState("");
  const [who, setWho] = useState("");
  const [kw, setKw] = useState("");
  const [amount, setAmount] = useState("");
  const [budget, setBudget] = useState("");
  const [title, setTitle] = useState("");
  const [timeline, setTimeline] = useState("");
  const [audience, setAudience] = useState("");
  const [notes, setNotes] = useState("");

  const [recs, setRecs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  async function findGrants(e) {
    e.preventDefault();
    setErr("");
    setLoading(true);
    setRecs([]);
    try {
      const r = await fetch(ENDPOINTS.find, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          organization: org,
          who,
          keywords: kw,
          amountRequested: Number(amount || 0),
          annualBudget: Number(budget || 0),
          projectTitle: title,
          timeline,
          audience,
          notes,
        }),
      });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || "Failed");
      setRecs(j.results || []);
    } catch (e) {
      setErr(e.message || "Could not fetch recommendations.");
    } finally {
      setLoading(false);
    }
  }

  async function checkout() {
    setErr("");
    try {
      const isTeacher = who === "Teacher (Classroom)";
      const r = await fetch(ENDPOINTS.checkout, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: org || "Client",
          who,
          category: who,          // server accepts category or who
          isTeacher,
          annualBudget: Number(budget || 0),
        }),
      });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || "Checkout failed.");
      window.location.href = j.url; // Stripe
    } catch (e) {
      setErr(e.message || "Checkout failed.");
    }
  }

  return (
    <div style={S.page}>
      <div style={S.card}>
        {/* Header */}
        <h1 style={S.h1}>GrantForgeUSA</h1>
        <p style={S.verse}>
          “Unless the Lord builds the house, the builders labor in vain.” — Psalm 127:1
        </p>

        {/* Intake */}
        <h3>Tell us about your project (Free Intake)</h3>
        <p style={{ marginTop: -6, color: "#5b7083" }}>
          Intake is free. You only pay if you want a full custom draft.
        </p>

        <form onSubmit={findGrants}>
          <label style={S.label}>
            Organization
            <input style={S.input} value={org} onChange={e=>setOrg(e.target.value)} placeholder="Your Organization" required />
          </label>

          <label style={S.label}>
            Who are you?
            <select style={S.input} value={who} onChange={e=>setWho(e.target.value)} required>
              <option value="">Select a category</option>
              {CATS.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>

          <label style={S.label}>
            Keywords (comma separated)
            <input style={S.input} value={kw} onChange={e=>setKw(e.target.value)} placeholder="e.g., STEM, food, youth" />
          </label>

          <label style={S.label}>
            Amount Requested (USD)
            <input style={S.input} type="number" min="0" value={amount} onChange={e=>setAmount(e.target.value)} placeholder="e.g., 2500" />
          </label>

          <label style={S.label}>
            Annual Budget (USD)
            <input style={S.input} type="number" min="0" value={budget} onChange={e=>setBudget(e.target.value)} placeholder="e.g., 60000" />
          </label>

          <label style={S.label}>
            Project Title
            <input style={S.input} value={title} onChange={e=>setTitle(e.target.value)} placeholder="Short name of the project" />
          </label>

          <label style={S.label}>
            Timeline
            <input style={S.input} value={timeline} onChange={e=>setTimeline(e.target.value)} placeholder="What do you need & when?" />
          </label>

          <label style={S.label}>
            Audience / Who benefits?
            <input style={S.input} value={audience} onChange={e=>setAudience(e.target.value)} placeholder="Who is served (students, vets, families)?" />
          </label>

          <label style={S.label}>
            Notes (optional)
            <textarea style={{...S.input, ...S.ta}} value={notes} onChange={e=>setNotes(e.target.value)} placeholder="Anything else we should know?" />
          </label>

          {err && <div style={S.warn}>{err}</div>}

          <button type="submit" style={S.btn} disabled={loading}>
            {loading ? "Working…" : "See Recommendations"}
          </button>
        </form>

        {/* Recommendations */}
        {recs.length > 0 && (
          <>
            <h3 style={{ marginTop: 22 }}>Recommended Opportunities</h3>
            <ul style={S.list}>
              {recs.map((g, i) => (
                <li key={i} style={S.li}>
                  <a href={g.program_url || "#"} target="_blank" rel="noreferrer" style={S.a}>{g.title}</a>
                  <div style={S.meta}>
                    {(g.min_amount ? `$${g.min_amount.toLocaleString()}` : "") +
                     (g.max_amount ? `–$${g.max_amount.toLocaleString()}` : "")}
                    {g.deadline ? ` — Deadline ${g.deadline}` : ""}
                    {typeof g.fit === "number" ? ` — Fit ${g.fit}%` : ""}
                    {typeof g.requires_match_percent === "number" ? ` — Match ${g.requires_match_percent}%` : ""}
                  </div>
                </li>
              ))}
            </ul>

            <button onClick={checkout} style={S.btn}>Proceed to Secure Payment</button>
          </>
        )}

        {/* Footer (copyright + AI disclosure only) */}
        <div style={S.footer}>
          <small>© 2025 GrantForgeUSA.</small><br />
          <small>Generated with AI assistance through GrantForgeUSA. You must review all content before submission.</small>
        </div>
      </div>
    </div>
  );
}
