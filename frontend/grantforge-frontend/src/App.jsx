// src/App.jsx
import { useEffect, useState } from "react";
import { shortlist, getPreview, createCheckoutSession, downloadUrlBySession } from "./fetcher";
import { API_BASE } from "./config";
import "./App.css";

/* -------- Success Screen (inline) -------- */
function ThanksScreen() {
  const [url, setUrl] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const sid = p.get("session_id");
    if (!sid) { setErr("Missing Stripe session id."); return; }
    setUrl(downloadUrlBySession(sid));
  }, []);

  return (
    <div className="wrap">
      <header className="brand">
        <h1>GrantForgeUSA</h1>
        <p><em>"Unless the Lord builds the house, the builders labor in vain."</em> — Psalm 127:1</p>
      </header>

      <section className="card">
        <h2>Payment Success</h2>
        {url ? (
          <p><a id="downloadLink" href={url}>Download Draft PDF</a></p>
        ) : (
          <p className="error">{err || "Preparing your file..."}</p>
        )}
        <p className="muted">Keep this link for your records. You can request edits before submission.</p>
      </section>

      <footer className="footer">
        <p>© 2025 GrantForgeUSA</p>
        <p className="muted">This product uses AI to generate previews and draft language. Review and edit before any submission.</p>
      </footer>
    </div>
  );
}

/* -------- Intake App -------- */
function IntakeApp() {
  const [org, setOrg] = useState("");
  const [who, setWho] = useState("");
  const [keywords, setKeywords] = useState("");
  const [amountRequested, setAmountRequested] = useState("");
  const [annualBudget, setAnnualBudget] = useState("");
  const [projectTitle, setProjectTitle] = useState("");
  const [timeline, setTimeline] = useState("");
  const [audience, setAudience] = useState("");
  const [notes, setNotes] = useState("");

  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState([]);
  const [previews, setPreviews] = useState({});
  const [error, setError] = useState("");

  function intakePayload() {
    return {
      organization: org,
      category: who,
      keywords,
      amountRequested: Number(amountRequested || 0),
      annualBudget: Number(annualBudget || 0),
      projectTitle,
      timeline,
      audience,
      notes,
    };
  }

  async function handleSeeRecommendations() {
    setError(""); setLoading(true); setResults([]); setPreviews({});
    try {
      const data = await shortlist(intakePayload());
      if (!data.ok) throw new Error(data.error || "Could not fetch recommendations.");
      setResults(data.results || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function handlePreview(row) {
    setError("");
    try {
      const data = await getPreview(intakePayload());
      if (!data.ok) throw new Error(data.error || "Preview failed.");
      setPreviews(p => ({ ...p, [row.title]: data.summary }));
    } catch (e) {
      setError(e.message);
    }
  }

  async function handlePay(row) {
    setError(""); setLoading(true);
    try {
      const body = { ...intakePayload(), grant: row };
      const data = await createCheckoutSession(body);
      if (!data.ok) throw new Error(data.error || "Checkout failed.");
      window.location.href = data.url; // Stripe hosted page
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="wrap">
      <header className="brand">
        <h1>GrantForgeUSA</h1>
        <p><em>"Unless the Lord builds the house, the builders labor in vain."</em> — Psalm 127:1</p>
      </header>

      <section className="card">
        <h2>Tell us about your project (Free Intake)</h2>
        <p className="muted">Intake is free. You only pay if you want a full custom draft.</p>

        <label>Organization
          <input value={org} onChange={e=>setOrg(e.target.value)} placeholder="Your organization" />
        </label>

        <label>Who are you?
          <select value={who} onChange={e=>setWho(e.target.value)}>
            <option value="">Select a category</option>
            <option>Teacher (Classroom)</option>
            <option>School / District</option>
            <option>Church / Faith Org</option>
            <option>501c3 Nonprofit</option>
            <option>Small Business</option>
            <option>City / Municipality</option>
            <option>Other</option>
          </select>
        </label>

        <label>Keywords (comma separated)
          <input value={keywords} onChange={e=>setKeywords(e.target.value)} placeholder="e.g., STEM, robotics, classroom equipment, Title 1" />
        </label>

        <div className="grid2">
          <label>Amount Requested (USD)
            <input type="number" value={amountRequested} onChange={e=>setAmountRequested(e.target.value)} placeholder="e.g., 2500" />
          </label>
          <label>Annual Budget (USD)
            <input type="number" value={annualBudget} onChange={e=>setAnnualBudget(e.target.value)} placeholder="e.g., 60000" />
          </label>
        </div>

        <label>Project Title
          <input value={projectTitle} onChange={e=>setProjectTitle(e.target.value)} placeholder="Short name of the project" />
        </label>

        <label>Timeline
          <input value={timeline} onChange={e=>setTimeline(e.target.value)} placeholder="What do you need & when?" />
        </label>

        <label>Audience / Who benefits?
          <input value={audience} onChange={e=>setAudience(e.target.value)} placeholder="Who is served (students, vets, etc.)" />
        </label>

        <label>Notes (optional)
          <textarea value={notes} onChange={e=>setNotes(e.target.value)} placeholder="Anything reviewers should know" rows={3} />
        </label>

        <button disabled={loading} onClick={handleSeeRecommendations}>See Recommendations</button>
        {error && <p className="error">{error}</p>}
      </section>

      {results.length > 0 && (
        <section className="results">
          <h3>Recommended Opportunities</h3>
          <ul>
            {results.map((row, i) => (
              <li key={i} className="result">
                <div className="row1">
                  <a href={row.program_url} target="_blank" rel="noopener noreferrer">{row.title}</a>
                  <span> — {row.amount} — Deadline {row.deadline} — Fit {row.fit}</span>
                </div>
                {row.fit_notes && <div className="notes">Notes: {row.fit_notes}</div>}

                <div className="actions">
                  <button onClick={()=>handlePreview(row)}>Preview (Free)</button>
                  <button onClick={()=>handlePay(row)}>Draft this (Pay)</button>
                </div>

                {previews[row.title] && (
                  <div className="preview">{previews[row.title]}</div>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      <footer className="footer">
        <p>© 2025 GrantForgeUSA</p>
        <p className="muted">
          This product uses AI to generate previews and draft language. Review and edit before any submission.
        </p>
      </footer>
    </div>
  );
}

/* -------- Top-level: route switch by pathname -------- */
export default function App() {
  if (typeof window !== "undefined" && window.location.pathname.startsWith("/thanks")) {
    return <ThanksScreen />;
  }
  return <IntakeApp />;
}
