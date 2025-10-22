// src/App.jsx — v11.1 vertical mobile-first layout
import { useState } from "react";
import { API_BASE } from "./config";
import { apiHealth, getShortlist } from "./fetcher";
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

  const [status, setStatus] = useState("");
  const [view, setView] = useState("intake"); // intake | shortlist
  const [results, setResults] = useState([]);
  const [message, setMessage] = useState(null);

  async function handleHealth() {
    setStatus("Checking backend…");
    try {
      const h = await apiHealth();
      setStatus(`Backend OK — ${new Date(h.ts).toLocaleTimeString()}`);
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
        audience
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
      <header>
        <h1>GrantForgeUSA</h1>
        <p className="verse">
          “Unless the Lord builds the house, the builders labor in vain.” — Psalm 127:1
        </p>
        <small>
          API: {API_BASE} —{" "}
          <button onClick={handleHealth}>Check Health</button>
          {status && <em> · {status}</em>}
        </small>
      </header>

      {view === "intake" && (
        <form onSubmit={handleIntakeSubmit} className="card vertical">
          <h2>Tell us about your project (Free Intake)</h2>

          <label>Organization</label>
          <input value={org} onChange={e => setOrg(e.target.value)} required placeholder="Your Organization" />

          <label>Who are you?</label>
          <select value={cat} onChange={e => setCat(e.target.value)}>
            {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>

          <label>Keywords (comma separated)</label>
          <input value={keywords} onChange={e => setKeywords(e.target.value)} placeholder="e.g. STEM, food, youth" />

          <label>Amount Requested (USD)</label>
          <input value={reqAmt} onChange={e => setReqAmt(e.target.value)} placeholder="e.g. 25000" />

          <label>Annual Budget (USD)</label>
          <input value={budget} onChange={e => setBudget(e.target.value)} placeholder="e.g. 120000" />

          <label>Project Title</label>
          <input value={projectTitle} onChange={e => setProjectTitle(e.target.value)} placeholder="Short project name" />

          <label>Timeline</label>
          <input value={timeline} onChange={e => setTimeline(e.target.value)} placeholder="When will the project run?" />

          <label>Audience / Who benefits?</label>
          <textarea
            value={audience}
            onChange={e => setAudience(e.target.value)}
            placeholder="Students, veterans, local families, etc."
          />

          <button type="submit" className="submit-btn">
            See Recommendations
          </button>

          <p className="muted">
            Intake is free. You only pay if you want your full draft.
          </p>
        </form>
      )}

      {view === "shortlist" && (
        <div className="card">
          <h2>Recommended Opportunities</h2>
          {message && <p className="warn">{message}</p>}
          <p>Choose one to continue. We’ll generate a short preview for free; full drafts are paid.</p>

          <ul className="list">
            {results.map((r, i) => (
              <li key={i} className={!r.eligible ? "dim" : ""}>
                <a href={r.program_url} target="_blank" rel="noreferrer" className="title">
                  {r.title}
                </a>
                <div className="meta">
                  {r.amount} — Deadline {r.deadline} — Match {r.requires_match_percent}% · Fit {r.fit} ({r.fit_score}%)
                </div>
                {!!(r.reasons && r.reasons.length) && (
                  <div className="reasons">
                    <strong>Notes:</strong> {r.reasons.join("; ")}
                  </div>
                )}
              </li>
            ))}
          </ul>

          <button onClick={backToIntake} className="back-btn">Back</button>
        </div>
      )}

      <footer>
        <small>© {new Date().getFullYear()} GrantForgeUSA — Built with faith, for those who build their communities.</small>
      </footer>
    </div>
  );
}
