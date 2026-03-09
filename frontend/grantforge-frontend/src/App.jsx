// src/App.jsx — production intake and checkout flow
import { useEffect, useState } from "react";
import {
  shortlist,
  getPreview,
  createCheckoutSession,
  createDownloadToken,
  downloadUrlByToken,
  receiptByToken,
} from "./fetcher";
import "./App.css";

/* -------- Safe Grants.gov direct opportunity URL helper -------- */
function safeProgramUrl(u, title, tags = [], row = {}) {
  const oppNumber = (row.opportunity_number || row.opp_number || row.oppNumber || "").trim();
  if (oppNumber) {
    return `https://www.grants.gov/search-results-detail/${encodeURIComponent(oppNumber)}`;
  }

  const official = row.official_url || row.program_url || u || "";
  if (typeof official === "string" && official.startsWith("http") && official.includes("grants.gov") && !official.includes("apply07.grants.gov") && !official.includes("grantsws/rest/opportunities/details")) {
    return official;
  }
  const q = encodeURIComponent([oppNumber, title, ...(tags || [])].filter(Boolean).join(" ") || "federal grants");
  return `https://www.grants.gov/search-grants?keywords=${q}`;
}

/* -------- Success Screen -------- */
function ThanksScreen() {
  const [url, setUrl] = useState("");
  const [err, setErr] = useState("");
  const [paid, setPaid] = useState(false);

  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const checkoutRef = p.get("ref");
    if (!checkoutRef) { setErr("Missing secure checkout reference."); return; }

    let mounted = true;
    let tries = 0;

    const poll = async () => {
      try {
        const t = await createDownloadToken(checkoutRef);
        if (t && t.ok && t.token) {
          const r = await receiptByToken(t.token);
          if (r && r.ok) {
            setPaid(!!r.paid);
            setUrl(downloadUrlByToken(t.token));
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
        setErr("Your payment is still finalizing. Please refresh in a moment.");
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
        <h2>Your grant narrative is ready</h2>
        {url ? (
          <p>
            <a id="downloadLink" href={url}>Download Grant Narrative PDF</a>
            {!paid && <span className="muted" style={{ marginLeft: 8 }}>(payment finalizing)</span>}
          </p>
        ) : (
          <p className="error">{err || "Preparing your file..."}</p>
        )}
        <p className="muted">Keep this link for your records and internal review workflow.</p>
      </section>

      <footer className="footer">
        <p>© 2025 GrantForgeUSA</p>
        <p className="muted">
          Review and edit all draft materials before submission.
        </p>
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
  const [notice, setNotice] = useState("");
  const [previewBusy, setPreviewBusy] = useState({}); // per-row preview spinner/lock
  const [fieldErrors, setFieldErrors] = useState({});

  const federalResults = results;

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
      includeExpired: false, // streamlined: never show expired
    };
  }

  function validateRequiredFields() {
    const errors = {};
    if (!org.trim()) errors.org = "Organization name is required.";
    if (!who.trim()) errors.who = "Please choose your organization category.";
    if (!keywords.trim()) errors.keywords = "Keywords are required.";
    if (!amountRequested.toString().trim()) errors.amountRequested = "Amount requested is required.";
    if (!annualBudget.toString().trim()) errors.annualBudget = "Annual budget is required.";
    if (!projectTitle.trim()) errors.projectTitle = "Project title is required.";
    if (!timeline.trim()) errors.timeline = "Implementation timeline is required.";
    if (!audience.trim()) errors.audience = "Target audience is required.";
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function handleSeeRecommendations() {
    setError("");
    if (!validateRequiredFields()) {
      setError("Please complete the required fields before continuing.");
      return;
    }
    setLoading(true);
    setResults([]);
    setPreviews({});
    setNotice("");
    try {
      const data = await shortlist(intakePayload());
      if (!data.ok) throw new Error(data.error || "Could not fetch recommendations.");
      setResults(data.results || []);
      setNotice(data.notice || "");
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
    if (!validateRequiredFields()) {
      setError("Please complete all required fields before checkout.");
      return;
    }
    setLoading(true);
    try {
      const body = {
        ...intakePayload(),
        grant: row,
        recommendations: federalResults.map((r) => ({
          title: r.title,
          program_url: safeProgramUrl(r.program_url, r.title, r.tags, r),
        })),
      };
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
        <h2>Tell us about your project</h2>
        <p className="muted">Flat fee: $2,500 per proposal draft. All sales final. No refunds.</p>
        <p className="muted" style={{ marginTop: 4 }}>Provide brief answers. We will match your project to federal grant opportunities.</p>
        <p className="muted" style={{ marginTop: 4 }}>
          We do not guarantee funding and do not submit grants on your behalf.
        </p>

        <label>Organization
          <input
            value={org}
            onChange={e=>setOrg(e.target.value)}
            required
          />
          {fieldErrors.org && <span className="error">{fieldErrors.org}</span>}
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
          {fieldErrors.who && <span className="error">{fieldErrors.who}</span>}
        </label>

        <label>Keywords (comma separated)
          <input
            value={keywords}
            onChange={e=>setKeywords(e.target.value)}
            required
          />
          {fieldErrors.keywords && <span className="error">{fieldErrors.keywords}</span>}
        </label>

        <div className="grid2">
          <label>Amount Requested (USD)
            <input
              type="number"
              value={amountRequested}
              onChange={e=>setAmountRequested(e.target.value)}
              
            />
            {fieldErrors.amountRequested && <span className="error">{fieldErrors.amountRequested}</span>}
          </label>
          <label>Annual Budget (USD)
            <input
              type="number"
              value={annualBudget}
              onChange={e=>setAnnualBudget(e.target.value)}
              
            />
            {fieldErrors.annualBudget && <span className="error">{fieldErrors.annualBudget}</span>}
          </label>
        </div>

        <label>Project Title
          <input
            value={projectTitle}
            onChange={e=>setProjectTitle(e.target.value)}
            
          />
          {fieldErrors.projectTitle && <span className="error">{fieldErrors.projectTitle}</span>}
        </label>

        <label>Implementation Timeline
          <input
            value={timeline}
            onChange={e=>setTimeline(e.target.value)}
            
          />
          {fieldErrors.timeline && <span className="error">{fieldErrors.timeline}</span>}
        </label>

        <label>Audience / Who benefits?
          <input
            value={audience}
            onChange={e=>setAudience(e.target.value)}
            
          />
          {fieldErrors.audience && <span className="error">{fieldErrors.audience}</span>}
        </label>

        <label>Notes (optional)
          <textarea
            value={notes}
            onChange={e=>setNotes(e.target.value)}
            
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
            We show a short list of good-fit federal opportunities based on category and keywords. A detailed draft PDF is provided
            after payment, with the official Grants.gov notice link for your selected opportunity.
          </p>

          {notice && <p className="muted">{notice}</p>}
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
                        {" — "}{row.fit}
                      </span>
                    </div>

                    {(() => {
                      const directUrl = safeProgramUrl(row.program_url, row.title, row.tags, row);
                      if (!directUrl) return null;
                      return (
                        <div className="muted" style={{ marginTop: 4 }}>
                          <a
                            href={directUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            View official notice on Grants.gov
                          </a>
                        </div>
                      );
                    })()}

                    {Array.isArray(row.tags) && row.tags.length > 0 && (
                      <div className="muted" style={{ marginTop: 4 }}>
                        Focus areas: {row.tags.join(", ")}
                      </div>
                    )}

                    {row.fit_notes && <div className="notes">Match notes: {row.fit_notes}</div>}

                    <div className="actions">
                      <button
                        onClick={()=>handlePreview(row)}
                        disabled={!!previewBusy[row.title] || loading}
                        aria-busy={!!previewBusy[row.title]}
                      >
                        {previewBusy[row.title] ? "Building preview…" : "Preview Narrative"}
                      </button>
                      <button onClick={()=>handlePay(row)} disabled={loading}>
                        Pay Now — $2,500
                      </button>
                    </div>

                    {previews[row.title] && (
                      <div className="preview">
                        <p className="muted">Narrative preview (your purchased draft includes complete formatting and full detail).</p>
                        <pre>{previews[row.title]}</pre>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="muted">No direct federal matches found. Showing closest opportunities.</p>
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
