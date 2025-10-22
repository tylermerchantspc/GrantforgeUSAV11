// src/App.jsx — v11.1 vertical flow (intake → recommend → checkout)
import { useState } from "react";
import { API_BASE, ENDPOINTS } from "./config";

// helper: POST JSON
async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export default function App() {
  // intake
  const [org, setOrg] = useState("");
  const [who, setWho] = useState(""); // category
  const [keywords, setKeywords] = useState("");
  const [amount, setAmount] = useState("");
  const [budget, setBudget] = useState("");
  const [title, setTitle] = useState("");
  const [timeline, setTimeline] = useState("");
  const [audience, setAudience] = useState("");

  // UI states
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [step, setStep] = useState("intake"); // intake | recs
  const [results, setResults] = useState([]);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [checkingOut, setCheckingOut] = useState(false);

  // categories (teacher separated from schools)
  const CATEGORIES = [
    "Teacher (Classroom)",
    "School (K–12)",
    "Nonprofit (501c3)",
    "Church / Faith-based",
    "Small Business (≤ $500k)",
    "Medium Business ($500k–$2M)",
    "Large Organization ($2M+)",
    "City / Municipality",
    "Community Club / Civic Group",
  ];

  function currency(n) {
    if (!n && n !== 0) return "";
    const x = Number(n);
    if (Number.isNaN(x)) return n;
    return x.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
  }

  async function handleRecommend() {
    setError("");
    if (!org.trim() || !who.trim()) {
      setError("Please enter your organization and choose a category.");
      return;
    }
    setLoading(true);
    try {
      const payload = {
        organization: org.trim(),
        who: who.trim(),
        keywords: keywords.trim(),
        amountRequested: Number(amount || 0),
        annualBudget: Number(budget || 0),
        title: title.trim(),
        timeline: timeline.trim(),
        audience: audience.trim(),
      };
      const data = await postJSON(ENDPOINTS.shortlist, payload);
      if (!data.ok) throw new Error(data.error || "Unable to get recommendations.");
      setResults(data.results || []);
      setSelectedIndex(-1);
      setStep("recs");
    } catch (e) {
      setError(e.message || "Failed to fetch recommendations.");
    } finally {
      setLoading(false);
    }
  }

  async function handleCheckout() {
    setError("");
    if (selectedIndex < 0) {
      setError("Please choose one opportunity to continue.");
      return;
    }
    const chosen = results[selectedIndex];

    // price logic (per-draft; teacher gets $9.99)
    const lower = (who || "").toLowerCase();
    const isTeacher = lower.includes("teacher");
    const price = isTeacher ? 9.99 : lower.includes("small business") ? 49.99 : lower.includes("medium business") ? 99.99 : lower.includes("large") ? 199.99 : lower.includes("school") ? 49.99 : lower.includes("nonprofit") ? 49.99 : lower.includes("church") ? 49.99 : lower.includes("city") ? 199.99 : 49.99;

    setCheckingOut(true);
    try {
      const body = {
        name: org.trim(),
        category: who.trim(),
        isTeacher: isTeacher,
        // we also send what they chose so it can be logged/embedded in the PDF stub later if desired
        chosenTitle: chosen.title,
        chosenProgram: chosen.program || "",
        chosenAmount: chosen.max_amount || chosen.min_amount || "",
        price,
      };
      const data = await postJSON(ENDPOINTS.checkout, body);
      if (!data.ok) throw new Error(data.error || "Checkout failed.");
      // redirect to Stripe
      window.location.href = data.url;
    } catch (e) {
      setError(e.message || "Checkout failed.");
    } finally {
      setCheckingOut(false);
    }
  }

  return (
    <div className="container">
      <div className="card vertical">
        <h1>GrantForgeUSA</h1>
        <p className="muted">
          <em>“Unless the Lord builds the house, the builders labor in vain.” — Psalm 127:1</em>
        </p>

        {step === "intake" && (
          <>
            <h3>Tell us about your project <span className="dim">(Free Intake)</span></h3>
            <p className="muted">Intake is free. You only pay if you want a full custom draft.</p>

            <label>
              Organization
              <input
                placeholder="Your Organization"
                value={org}
                onChange={(e) => setOrg(e.target.value)}
              />
            </label>

            <label>
              Who are you?
              <select value={who} onChange={(e) => setWho(e.target.value)}>
                <option value="">Select a category…</option>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </label>

            <label>
              Keywords (comma separated)
              <input
                placeholder="e.g., STEM, food, youth"
                value={keywords}
                onChange={(e) => setKeywords(e.target.value)}
              />
            </label>

            <label>
              Amount Requested (USD)
              <input
                type="number"
                placeholder="e.g., 2500"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </label>

            <label>
              Annual Budget (USD)
              <input
                type="number"
                placeholder="e.g., 60000"
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
              />
            </label>

            <label>
              Project Title
              <input
                placeholder="Short name of the project"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </label>

            <label>
              Timeline
              <input
                placeholder="What do you need & when?"
                value={timeline}
                onChange={(e) => setTimeline(e.target.value)}
              />
            </label>

            <label>
              Audience / Who benefits?
              <input
                placeholder="Who is served (students, veterans, community, etc.)"
                value={audience}
                onChange={(e) => setAudience(e.target.value)}
              />
            </label>

            {error && <div className="warn">{error}</div>}

            <button className="submit-btn" onClick={handleRecommend} disabled={loading}>
              {loading ? "Working…" : "See Recommendations"}
            </button>

            <small className="muted">
              Private beta build · {new Date().getFullYear()}
            </small>
          </>
        )}

        {step === "recs" && (
          <>
            <h3>Recommended Opportunities</h3>
            <p className="muted">
              Choose one opportunity to continue. We’ll create a full draft only if you decide to purchase.
            </p>

            <ul className="list">
              {results.map((g, i) => (
                <li key={i}>
                  <label style={{ display: "flex", gap: "10px", alignItems: "flex-start", cursor: "pointer" }}>
                    <input
                      type="radio"
                      name="grantpick"
                      checked={selectedIndex === i}
                      onChange={() => setSelectedIndex(i)}
                      style={{ marginTop: "6px" }}
                    />
                    <div>
                      <a className="title" href={g.program_url || "#"} target="_blank" rel="noreferrer">
                        {g.title}
                      </a>
                      <div className="meta">
                        {g.max_amount || g.min_amount ? (
                          <>
                            {g.min_amount ? `${currency(g.min_amount)} ` : ""}
                            {g.max_amount ? (g.min_amount ? "– " : "") + `${currency(g.max_amount)}` : ""}
                            {" "}· Deadline {g.deadline || "TBD"}
                          </>
                        ) : (
                          <>Deadline {g.deadline || "TBD"}</>
                        )}
                        {typeof g.fit === "number" && (
                          <> — Fit <strong>{g.fit}%</strong></>
                        )}
                        {g.requires_match_percent > 0 && (
                          <> — Match Required: {g.requires_match_percent}%</>
                        )}
                        {g.eligible_types?.length ? (
                          <> — Eligible: {g.eligible_types.join(", ")}</>
                        ) : null}
                      </div>
                    </div>
                  </label>
                </li>
              ))}
            </ul>

            {error && <div className="warn" style={{ marginTop: 8 }}>{error}</div>}

            <button className="submit-btn" onClick={handleCheckout} disabled={checkingOut}>
              {checkingOut ? "Opening Checkout…" : "Get Full Custom Draft"}
            </button>

            <button className="back-btn" onClick={() => setStep("intake")} style={{ marginTop: 8 }}>
              Back
            </button>

            <small className="muted" style={{ marginTop: 8 }}>
              Intake is free. You’ll only be charged if you continue to purchase a draft.
            </small>
          </>
        )}
      </div>
    </div>
  );
}
