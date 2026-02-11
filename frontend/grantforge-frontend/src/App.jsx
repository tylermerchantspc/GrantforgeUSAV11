// src/App.jsx — v1.5 (revenue-ready; Grants.gov links; backend v11.2 aligned)
import { useEffect, useState } from "react";
import {
  shortlist,
  getPreview,
  createCheckoutSession,
  downloadUrlBySession,
  receiptBySession,
  API_BASE,
} from "./fetcher";
import "./App.css";

/* -------- US States + DC -------- */
const STATES = [
  { value: "", label: "Select a state (optional)" },
  { value: "AL", label: "AL — Alabama" }, { value: "AK", label: "AK — Alaska" },
  { value: "AZ", label: "AZ — Arizona" }, { value: "AR", label: "AR — Arkansas" },
  { value: "CA", label: "CA — California" }, { value: "CO", label: "CO — Colorado" },
  { value: "CT", label: "CT — Connecticut" }, { value: "DE", label: "DE — Delaware" },
  { value: "DC", label: "DC — District of Columbia" }, { value: "FL", label: "FL — Florida" },
  { value: "GA", label: "GA — Georgia" }, { value: "HI", label: "HI — Hawaii" },
  { value: "ID", label: "ID — Idaho" }, { value: "IL", label: "IL — Illinois" },
  { value: "IN", label: "IN — Indiana" }, { value: "IA", label: "IA — Iowa" },
  { value: "KS", label: "KS — Kansas" }, { value: "KY", label: "KY — Kentucky" },
  { value: "LA", label: "LA — Louisiana" }, { value: "ME", label: "ME — Maine" },
  { value: "MD", label: "MD — Maryland" }, { value: "MA", label: "MA — Massachusetts" },
  { value: "MI", label: "MI — Michigan" }, { value: "MN", label: "MN — Minnesota" },
  { value: "MS", label: "MS — Mississippi" }, { value: "MO", label: "MO — Missouri" },
  { value: "MT", label: "MT — Montana" }, { value: "NE", label: "NE — Nebraska" },
  { value: "NV", label: "NV — Nevada" }, { value: "NH", label: "NH — New Hampshire" },
  { value: "NJ", label: "NJ — New Jersey" }, { value: "NM", label: "NM — New Mexico" },
  { value: "NY", label: "NY — New York" }, { value: "NC", label: "NC — North Carolina" },
  { value: "ND", label: "ND — North Dakota" }, { value: "OH", label: "OH — Ohio" },
  { value: "OK", label: "OK — Oklahoma" }, { value: "OR", label: "OR — Oregon" },
  { value: "PA", label: "PA — Pennsylvania" }, { value: "RI", label: "RI — Rhode Island" },
  { value: "SC", label: "SC — South Carolina" }, { value: "SD", label: "SD — South Dakota" },
  { value: "TN", label: "TN — Tennessee" }, { value: "TX", label: "TX — Texas" },
  { value: "UT", label: "UT — Utah" }, { value: "VT", label: "VT — Vermont" },
  { value: "VA", label: "VA — Virginia" }, { value: "WA", label: "WA — Washington" },
  { value: "WV", label: "WV — West Virginia" }, { value: "WI", label: "WI — Wisconsin" },
  { value: "WY", label: "WY — Wyoming" },
];

/* -------- (Kept for future) Safe Grants.gov URL helper -------- */
function safeProgramUrl(u, title, tags = []) {
  try {
    if (typeof u === "string" && u.startsWith("http") && u.includes("grants.gov")) return u;
  } catch {}
  const q = encodeURIComponent(
    [...(title || "").split(/\s+/).slice(0, 6), ...(tags || []).slice(0, 4)].join(" ")
  );
  return `https://www.grants.gov/search-grants?keywords=${q}`;
}

/* -------- Success Screen -------- */
function ThanksScreen() {
  const [url, setUrl] = useState("");
  const [err, setErr] = useState("");
  const [paid, setPaid] = useState(false);

  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const sid = p.get("session_id");
    if (!sid) { setErr("Missing Stripe session id."); return; }

    let mounted = true;
    let tries = 0;

    const poll = async () => {
      try {
        const r = await receiptBySession(sid);
        if (r && r.ok) {
          setPaid(!!r.paid);
          if (r.download_path) {
            setUrl(`${API_BASE}${r.download_path}`);
            return;
          }
        }
      } catch {
        // ignore and keep polling
      }
      tries += 1;
      if (mounted && tries < 15) {
        setTimeout(poll, 2000);
      } else if (mounted && !url) {
        // fallback: computed URL (even if webhook/receipt log lagged)
        setUrl(downloadUrlBySession(sid));
      }
    };

    poll();
    return () => { mounted = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
          <p>
            <a id="downloadLink" href={url}>Download Draft PDF</a>
            {!paid && <span className="muted" style={{ marginLeft: 8 }}>(finalizing… ok to click)</span>}
          </p>
        ) : (
          <p className="error">{err || "Preparing your file..."}</p>
        )}
        <p className="muted">
          Keep this link for your records. You can request edits before any submission.
        </p>
        <p className="policy-note"><strong>All sales are final. No refunds.</strong></p>
      </section>

      <footer className="footer">
        <p>© 2025 GrantForgeUSA</p>
        <p className="muted">
          This product uses proprietary software to generate draft language. Review and edit before submitting to any funder.
        </p>
      </footer>
    </div>
  );
}

/* -------- Intake App -------- */
function IntakeApp() {
  const [org, setOrg] = useState("");
  const [who, setWho] = useState("");
  const [stateUS, setStateUS] = useState("");
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
  const [previewBusy, setPreviewBusy] = useState({}); // per-row preview spinner/lock

  const stateResults = results.filter(row => (row.level || "").toLowerCase() === "state");
  const federalResults = results.filter(row => (row.level || "").toLowerCase() !== "state");

  function intakePayload() {
    return {
      organization: org,
      category: who,
      state: stateUS,
      keywords,
      amountRequested: Number(amountRequested || 0),
      annualBudget: Number(annualBudget || 0),
      projectTitle,
      timeline,
      audience,
      notes,
      includeExpired: false, // streamlined: never show expired
    };
  }

  async function handleSeeRecommendations() {
    setError("");
    setLoading(true);
    setResults([]);
    setPreviews({});
    try {
      const data = await shortlist(intakePayload());
      if (!data.ok) throw new Error(data.error || "Could not fetch recommendations.");
      setResults(data.results || []);
    } catch (e) {
      setError(e.message || "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function handlePreview(row) {
    setError("");
    setPreviewBusy(p => ({ ...p, [row.title]: true }));
    try {
      const data = await getPreview({ ...intakePayload(), grant: row });
      if (!data.ok) throw new Error(data.error || "Preview failed.");
      setPreviews(p => ({ ...p, [row.title]: data.summary }));
    } catch (e) {
      setError(e.message || "Preview failed. Please try again.");
    } finally {
      setPreviewBusy(p => ({ ...p, [row.title]: false }));
    }
  }

  async function handlePay(row) {
    setError("");
    setLoading(true);
    try {
      const body = { ...intakePayload(), grant: row };
      const data = await createCheckoutSession(body);
      if (!data.ok) throw new Error(data.error || "Checkout failed.");
      window.location.href = data.url;
    } catch (e) {
      setError(e.message || "Checkout failed. Please try again or contact support.");
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
        <p className="muted">
          Intake and recommendations are free. You only pay when you choose to generate a full custom draft PDF.
        </p>
        <p className="muted" style={{ marginTop: 4 }}>
          Typical pricing: Teachers ≈ <strong>$9.99</strong> per draft. Most orgs ≈ <strong>$49–$199</strong>,
          automatically sized to your budget.
        </p>
        <p className="policy-note">All sales are final. No refunds.</p>

        <label>Organization
          <input
            value={org}
            onChange={e=>setOrg(e.target.value)}
            placeholder="Your organization"
          />
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

        <label>State (optional)
          <select value={stateUS} onChange={e=>setStateUS(e.target.value)}>
            {STATES.map(s => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </label>

        <label>Keywords (comma separated)
          <input
            value={keywords}
            onChange={e=>setKeywords(e.target.value)}
            placeholder="e.g., STEM, robotics, classroom equipment, Title 1"
          />
        </label>

        <div className="grid2">
          <label>Amount Requested (USD)
            <input
              type="number"
              value={amountRequested}
              onChange={e=>setAmountRequested(e.target.value)}
              placeholder="e.g., 2500"
            />
          </label>
          <label>Annual Budget (USD)
            <input
              type="number"
              value={annualBudget}
              onChange={e=>setAnnualBudget(e.target.value)}
              placeholder="e.g., 60000"
            />
          </label>
        </div>

        <label>Project Title
          <input
            value={projectTitle}
            onChange={e=>setProjectTitle(e.target.value)}
            placeholder="Short name of the project"
          />
        </label>

        <label>What do you need & when?
          <input
            value={timeline}
            onChange={e=>setTimeline(e.target.value)}
            placeholder="What do you need & when?"
          />
        </label>

        <label>Audience / Who benefits?
          <input
            value={audience}
            onChange={e=>setAudience(e.target.value)}
            placeholder="Who is served (students, vets, etc.)"
          />
        </label>

        <label>Notes (optional)
          <textarea
            value={notes}
            onChange={e=>setNotes(e.target.value)}
            placeholder="Anything reviewers should know"
            rows={3}
          />
        </label>

        <button disabled={loading} onClick={handleSeeRecommendations}>
          {loading ? "Finding matches..." : "See Recommendations"}
        </button>
        {error && <p className="error">{error}</p>}
      </section>

      {results.length > 0 && (
        <section className="results">
          <h3>Recommended Opportunities</h3>
          <p className="muted">
            We show a short list of good fits. State options appear first when provided. A detailed draft PDF is provided
            after payment, and you’ll get the official Grants.gov link with your draft.
          </p>

          {stateResults.length > 0 && (
            <div className="results-group">
              <h4>State Opportunities</h4>
              <ul>
                {stateResults.map((row, i) => (
                  <li key={`state-${i}`} className="result">
                    <div className="row1">
                      <strong>{row.title}</strong>
                      <span>
                        {" — "}{row.amount}
                        {" — Deadline "}{row.deadline}
                      </span>
                    </div>

                    {row.program_url && (
                      <div className="muted" style={{ marginTop: 4 }}>
                        <a
                          href={row.program_url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          Open state funding search
                        </a>
                      </div>
                    )}

                    {row.grant_number && <div className="muted">Grant #: {row.grant_number}</div>}
                    {row.fit_notes && <div className="notes">Notes: {row.fit_notes}</div>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {federalResults.length > 0 ? (
            <div className="results-group">
              <h4>Federal Opportunities</h4>
              <ul>
                {federalResults.map((row, i) => (
                  <li key={`fed-${i}`} className="result">
                    <div className="row1">
                      <strong>{row.title}</strong>
                      <span>
                        {" — up to "}{row.amount}
                        {" — Deadline "}{row.deadline}
                        {" — Fit "}{row.fit}
                      </span>
                    </div>

                    {row.program_url && (
                      <div className="muted" style={{ marginTop: 4 }}>
                        <a
                          href={row.program_url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          View official notice on Grants.gov
                        </a>
                      </div>
                    )}

                    {Array.isArray(row.tags) && row.tags.length > 0 && (
                      <div className="muted" style={{ marginTop: 4 }}>
                        Focus areas: {row.tags.join(", ")}
                      </div>
                    )}

                    {row.grant_number && <div className="muted">Grant #: {row.grant_number}</div>}
                    {row.fit_notes && <div className="notes">Fit notes: {row.fit_notes}</div>}

                    <div className="actions">
                      <button
                        onClick={()=>handlePreview(row)}
                        disabled={!!previewBusy[row.title] || loading}
                        aria-busy={!!previewBusy[row.title]}
                      >
                        {previewBusy[row.title] ? "Building preview…" : "See Sample Language (Free)"}
                      </button>
                      <button onClick={()=>handlePay(row)} disabled={loading}>
                        Generate Full Draft (Pay)
                      </button>
                    </div>

                    {previews[row.title] && (
                      <div className="preview">
                        <p className="muted">Sample only — your paid draft is longer and fully formatted.</p>
                        <pre>{previews[row.title]}</pre>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="muted">No federal opportunities matched this intake. Adjust your keywords and try again.</p>
          )}
        </section>
      )}

      <footer className="footer">
        <p>© 2025 GrantForgeUSA</p>
        <p className="muted">
          This product uses a proprietary drafting engine to generate previews and draft language. Review and edit before
          any submission.
        </p>
      </footer>
    </div>
  );
}

/* -------- Router switch -------- */
export default function App() {
  if (typeof window !== "undefined" && window.location.pathname.startsWith("/thanks")) {
    return <ThanksScreen />;
  }
  return <IntakeApp />;
}
