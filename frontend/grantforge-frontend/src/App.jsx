// src/App.jsx — v11 Intake → Recommendations (money-match aware)
import { useState } from "react";
import { API_BASE, ENDPOINTS } from "./config";
import { apiHealth, getShortlist, getDraft } from "./fetcher";
import "./App.css";

const CATEGORIES = [
  "Teacher (Classroom)",
  "School",
  "501c3",
  "Church / Faith-based",
  "Community Club / Nonprofit (non-501c3)",
  "Small Business",
  "Municipality (City/County)"
];

export default function App() {
  const [org, setOrg] = useState("");
  const [cat, setCat] = useState(CATEGORIES[0]);
  const [keywords, setKeywords] = useState("");
  const [reqAmt, setReqAmt] = useState("");
  const [budget, setBudget] = useState("");
  const [timeline, setTimeline] = useState("");
  const [projectTitle, setProjectTitle] = useState("");
  const [audience, setAudience] = useState("");
  const [outcomes, setOutcomes] = useState("");

  const [status, setStatus] = useState("");
  const [view, setView] = useState("intake"); // intake | shortlist
  const [results, setResults] = useState([]);
  const [message, setMessage] = useState(null);

  async function handleHealth() {
    setStatus("Checking backend…");
    try {
      const h = await apiHealth();
      setStatus(`OK — ${h.grantsCount} local programs · ${new Date(h.ts).toLocaleTimeString()}`);
    } catch {
      setStatus("Health check failed");
    }
  }

  async function handleIntakeSubmit(e) {
    e?.preventDefault?.();
    setStatus("Scoring…");
    setResults([]);
    try {
      const payload = {
        organization: org,
        category: cat,
        keywords,
        amountRequested: reqAmt,
        budget,
        timeline,
        projectTitle,
        audience,
        outcomes
      };
      const r = await getShortlist(payload);
      setResults(r.results || []);
      setMessage(r.message || null);
      setView("shortlist");
      setStatus("");
    } catch (err) {
      setStatus("Error: could not score opportunities.");
      console.error(err);
    }
  }

  function backToIntake() {
    setView("intake");
    setMessage(null);
  }

  return (
    <div className="container">
      <header style={{ marginBottom: 18 }}>
        <h1>GrantForgeUSA</h1>
        <p style={{ margin: 0, color: "#666" }}>
          “Unless the Lord builds the house, the builders labor in vain.” — Psalm 127:1
        </p>
        <small>API: {API_BASE} — <button onClick={handleHealth}>Check Health</button> {status && <em> · {status}</em>}</small>
      </header>

      {view === "intake" && (
        <form onSubmit={handleIntakeSubmit} className="card">
          <h2>Tell us about your project (free)</h2>
          <div className="row">
            <label>Organization</label>
            <input value={org} onChange={e => setOrg(e.target.value)} placeholder="Your Organization" required />
          </div>

          <div className="row">
            <label>Who are you?</label>
            <select value={cat} onChange={e => setCat(e.target.value)}>
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>

          <div className="row">
            <label>Keywords (comma separated)</label>
            <input value={keywords} onChange={e => setKeywords(e.target.value)} placeholder="after-school, STEM, equipment" />
          </div>

          <div className="row two">
            <div>
              <label>Amount Requested (USD)</label>
              <input value={reqAmt} onChange={e => setReqAmt(e.target.value)} placeholder="e.g. 25000" />
            </div>
            <div>
              <label>Annual Budget (USD)</label>
              <input value={budget} onChange={e => setBudget(e.target.value)} placeholder="e.g. 120000" />
            </div>
          </div>

          <div className="row">
            <label>Project Title</label>
            <input value={projectTitle} onChange={e => setProjectTitle(e.target.value)} placeholder="Short name of the project" />
          </div>

          <div className="row">
            <label>Timeline</label>
            <input value={timeline} onChange={e => setTimeline(e.target.value)} placeholder="When do you expect to start/finish?" />
          </div>

          <div className="row">
            <label>Audience / Who benefits?</label>
            <textarea value={audience} onChange={e => setAudience(e.target.value)} placeholder="Students, veterans, neighborhood, etc." />
          </div>

          <div className="row">
            <label>Expected Outcomes (1–3)</label>
            <textarea value={outcomes} onChange={e => setOutcomes(e.target.value)} placeholder="Measurable results you expect" />
          </div>

          <div className="row">
            <button type="submit">See Recommendations</button>
          </div>

          <p className="muted">Intake is free. You only pay if you want a full custom draft.</p>
        </form>
      )}

      {view === "shortlist" && (
        <div className="card">
          <h2>Recommended Opportunities</h2>
          {message && <p className="warn">{message}</p>}
          <p>Choose one to continue. We’ll generate a short preview for free; the full draft is paid.</p>

          <ul className="list">
            {results.map((r, i) => (
              <li key={i} className={!r.eligible ? "dim" : ""}>
                <div className="row space">
                  <div>
                    <a href={r.program_url} target="_blank" rel="noreferrer" className="title">{r.title}</a>
                    <div className="meta">
                      {r.amount} — Deadline {r.deadline} — Match {r.requires_match_percent}%
                      {" · "}Fit {r.fit} ({r.fit_score}%){!r.eligible ? " — Not eligible" : ""}
                    </div>
                  </div>
                </div>
                {!!(r.reasons && r.reasons.length) && (
                  <div className="reasons">
                    <strong>Why / Notes:</strong> {r.reasons.join("; ")}
                  </div>
                )}
              </li>
            ))}
          </ul>

          <div className="row">
            <button onClick={backToIntake}>Back</button>
          </div>
        </div>
      )}

      <footer style={{ marginTop: 40 }}>
        <small>© {new Date().getFullYear()} GrantForgeUSA. Intake & preview free. Draft fee shown before payment.</small>
      </footer>
    </div>
  );
}
