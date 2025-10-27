// src/App.jsx — Intake → shortlist (with links) → preview → pay → download by session
import { useState } from "react";
import { API_BASE } from "./config";

async function api(path, body) {
  const r = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export default function App() {
  const [form, setForm] = useState({
    organization: "",
    category: "",
    keywords: "",
    amountRequested: "",
    annualBudget: "",
    projectTitle: "",
    timeline: "",
    audience: "",
    notes: "",
  });
  const [results, setResults] = useState([]);
  const [previews, setPreviews] = useState({});
  const [err, setErr] = useState("");
  const [paying, setPaying] = useState("");

  function setField(k, v) {
    setForm((s) => ({ ...s, [k]: v }));
  }

  async function handleRecommend() {
    setErr("");
    setResults([]);
    setPreviews({});
    try {
      const r = await api("/questionnaire", form);
      if (!r.ok) throw new Error(r.error || "Bad response");
      setResults(r.results || []);
      if (!r.results || !r.results.length) {
        setErr("No programs matched your inputs. Try adjusting keywords/amount.");
      }
    } catch (e) {
      setErr("Could not fetch recommendations.");
      console.error(e);
    }
  }

  async function handlePreview(g) {
    try {
      const r = await api("/preview", { intake: form, grant: g });
      if (r.ok) {
        setPreviews((p) => ({ ...p, [g.id]: r.text }));
      }
    } catch (e) {
      console.error(e);
    }
  }

  async function handlePay(g) {
    setErr("");
    setPaying(g.id);
    try {
      const r = await api("/create-checkout-session", { intake: form, grant: g });
      if (!r.ok) throw new Error(r.error || "Stripe error");
      window.location.href = r.url;
    } catch (e) {
      setErr("Payment could not start. Please try again.");
      console.error(e);
    } finally {
      setPaying("");
    }
  }

  // Thank-you page (download)
  if (window.location.pathname === "/thanks") {
    const sid = new URLSearchParams(window.location.search).get("session_id") || "";
    return (
      <div style={{ maxWidth: 860, margin: "40px auto", fontFamily: "system-ui, sans-serif" }}>
        <h1>GrantForgeUSA</h1>
        <p><em>“Unless the Lord builds the house, the builders labor in vain.” — Psalm 127:1</em></p>
        <h2>Payment Success</h2>
        {sid ? (
          <p>
            <a href={`${API_BASE}/download-by-session?session_id=${encodeURIComponent(sid)}`}>
              Download Draft PDF
            </a>
          </p>
        ) : (
          <p>Session confirmed.</p>
        )}
        <p>Keep this link for your records. You can request edits before submission.</p>
        <footer style={{ marginTop: 32, fontSize: 12, opacity: 0.8 }}>
          © 2025 GrantForgeUSA • This product uses AI to generate previews and draft language.
          Review and edit before any submission.
        </footer>
      </div>
    );
  }

  const categories = [
    "Teacher (Classroom)",
    "School / District",
    "Small Nonprofit / Club / Small Business / Church",
    "Medium Nonprofit (500k–2M)",
    "Large Nonprofit / City / Municipality",
    "Other",
  ];

  return (
    <div style={{ maxWidth: 860, margin: "24px auto", fontFamily: "system-ui, sans-serif" }}>
      <h1>GrantForgeUSA</h1>
      <p><em>“Unless the Lord builds the house, the builders labor in vain.” — Psalm 127:1</em></p>

      <h2>Tell us about your project (Free Intake)</h2>
      <p style={{ marginTop: -6 }}>Intake is free. You only pay if you want a full custom draft.</p>

      <div style={{ display: "grid", gap: 10 }}>
        <input
          placeholder="Organization"
          value={form.organization}
          onChange={(e) => setField("organization", e.target.value)}
        />
        <select value={form.category} onChange={(e) => setField("category", e.target.value)}>
          <option value="">Who are you? (Select a category)</option>
          {categories.map((c) => (<option key={c} value={c}>{c}</option>))}
        </select>
        <input
          placeholder="Keywords (comma separated) — e.g., STEM, food, youth"
          value={form.keywords}
          onChange={(e) => setField("keywords", e.target.value)}
        />
        <input
          placeholder="Amount Requested (USD) — e.g., 2500"
          value={form.amountRequested}
          onChange={(e) => setField("amountRequested", e.target.value)}
        />
        <input
          placeholder="Annual Budget (USD) — e.g., 60000"
          value={form.annualBudget}
          onChange={(e) => setField("annualBudget", e.target.value)}
        />
        <input
          placeholder="Project Title"
          value={form.projectTitle}
          onChange={(e) => setField("projectTitle", e.target.value)}
        />
        <input
          placeholder="Timeline"
          value={form.timeline}
          onChange={(e) => setField("timeline", e.target.value)}
        />
        <input
          placeholder="Audience / Who benefits?"
          value={form.audience}
          onChange={(e) => setField("audience", e.target.value)}
        />
        <textarea
          placeholder="Notes (optional)"
          value={form.notes}
          onChange={(e) => setField("notes", e.target.value)}
          rows={3}
        />
        <button onClick={handleRecommend}>See Recommendations</button>
      </div>

      {err && <p style={{ color: "crimson", marginTop: 12 }}>{err}</p>}

      {results.length > 0 && (
        <>
          <h3 style={{ marginTop: 24 }}>Recommended Opportunities</h3>
          <ul style={{ paddingLeft: 18 }}>
            {results.map((g) => (
              <li key={g.id} style={{ marginBottom: 20 }}>
                <div>
                  <a href={g.program_url} target="_blank" rel="noreferrer">{g.title}</a>
                  {" — "}
                  <span>{g.amount_range}</span>
                  {" — Deadline "}
                  <span>{g.deadline}</span>
                  {" — Fit "}
                  <strong>{g.fit}</strong>
                </div>
                <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
                  <button onClick={() => handlePreview(g)}>Preview (Free)</button>
                  <button disabled={paying === g.id} onClick={() => handlePay(g)}>
                    {paying === g.id ? "Starting checkout…" : "Draft this (Pay)"}
                  </button>
                </div>
                {previews[g.id] && (
                  <div style={{ marginTop: 10, background: "#f6f8fa", padding: 10, borderRadius: 6 }}>
                    <div dangerouslySetInnerHTML={{ __html: previews[g.id].replace(/\n/g, "<br/>") }} />
                  </div>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      <footer style={{ marginTop: 32, fontSize: 12, opacity: 0.8 }}>
        © 2025 GrantForgeUSA • This product uses AI to generate previews and draft language.
        Review and edit before any submission.
      </footer>
    </div>
  );
}
