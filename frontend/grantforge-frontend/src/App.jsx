// src/App.jsx — GrantForgeUSA v1.1 (Patch 1)
// Intake-only landing → Matches → Free Preview → Paid Full Draft (Stripe test) → Success
// Teacher is a separate category with $9.99 fee. Others priced by budget tier.
// We store intake in sessionStorage so the /success page can show the full draft.

import { useEffect, useMemo, useState } from "react";
import { API_BASE, ENDPOINTS } from "./config";

const CATS = [
  "Teacher / Individual Classroom",
  "School / Education Program",
  "501(c)(3) Nonprofit",
  "Church / Faith-Based Ministry",
  "Small Business",
  "City / County / Municipality",
  "Community Project / Club / Civic Group",
  "Other",
];

function calcFee(category, budgetStr) {
  const isTeacher = category === "Teacher / Individual Classroom";
  if (isTeacher) return 9.99;
  const n = Number(String(budgetStr || "0").replace(/[^0-9.]/g, "")) || 0;
  if (n <= 500000) return 49.99;
  if (n <= 2000000) return 99.99;
  return 199.99;
}

function prettyUSD(n) {
  try {
    return n.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 });
  } catch {
    return `$${Number(n).toFixed(2)}`;
  }
}

function saveSession(key, val) {
  try { sessionStorage.setItem(key, JSON.stringify(val)); } catch {}
}
function loadSession(key, fallback = null) {
  try {
    const v = sessionStorage.getItem(key);
    return v ? JSON.parse(v) : fallback;
  } catch { return fallback; }
}
function clearSession(key) { try { sessionStorage.removeItem(key); } catch {} }

export default function App() {
  // Route gate for Success page (after Stripe redirect)
  const isSuccessRoute = typeof window !== "undefined" && window.location.pathname === "/success";

  // -------- health banner (optional) --------
  const [health, setHealth] = useState(null);
  useEffect(() => {
    fetch(ENDPOINTS.health).then(r => r.json()).then(setHealth).catch(() => {});
  }, []);

  // -------- intake state --------
  const [org, setOrg] = useState("");
  const [category, setCategory] = useState(CATS[0]);
  const [budget, setBudget] = useState(""); // numeric string
  const [purpose, setPurpose] = useState("");
  const [timeline, setTimeline] = useState("");

  // calculated fee
  const fee = useMemo(() => calcFee(category, budget), [category, budget]);

  // -------- flow state --------
  const [step, setStep] = useState(isSuccessRoute ? "success" : "intake");
  const [matches, setMatches] = useState([]);
  const [selectedIdx, setSelectedIdx] = useState(-1);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  // If on /success, try to load saved intake to show the full draft
  useEffect(() => {
    if (isSuccessRoute) {
      const saved = loadSession("gf_intake", null);
      if (saved) {
        // Simulate a "full draft" by extending preview with richer text
        setOrg(saved.org);
        setCategory(saved.category);
        setBudget(saved.budget);
        setPurpose(saved.purpose);
        setTimeline(saved.timeline || "");
        setMatches(saved.matches || []);
        setSelectedIdx(saved.selectedIdx ?? -1);

        // Build a fuller draft using the previous preview outline if present
        const outline = saved.preview?.outline || saved.preview || {
          Summary: `${saved.org} seeks support for a ${saved.purpose} project.`,
          Need: `There is a documented need around ${saved.purpose} in the service area.`,
          Objectives: ["Objective 1", "Objective 2", "Objective 3"],
          Methods: ["Method A", "Method B"],
          "Budget Narrative": "Funds will support staff time, supplies, and outreach.",
          Impact: "Expected outcomes include improved access and measurable gains.",
          Compliance: "We will follow all program rules and reporting requirements."
        };

        const fullDraft = Object.entries(outline).map(([k, v]) => {
          if (Array.isArray(v)) {
            return `## ${k}\n- ${v.join("\n- ")}\n`;
          }
          return `## ${k}\n${v}\n`;
        }).join("\n");

        setPreview({ outline, fullDraft });
      }
    }
  }, [isSuccessRoute]);

  // ------- handlers -------
  async function handleStartIntake(e) {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      const body = {
        organization: org || "Your Organization",
        category,
        keywords: purpose || "general",
        timeline: timeline || ""
      };
      const r = await fetch(ENDPOINTS.shortlist, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || "Server error");
      setMatches(j.results || []);
      setSelectedIdx(-1);
      setStep("matches");
    } catch (e2) {
      setErr(e2.message || "Failed to start intake");
    } finally {
      setBusy(false);
    }
  }

  async function handleGeneratePreview() {
    if (selectedIdx < 0) return;
    setErr("");
    setBusy(true);
    try {
      // Call backend /draft to get a neutral preview outline
      const body = {
        organization: org || "Your Organization",
        topic: purpose || "community"
      };
      const r = await fetch(ENDPOINTS.draft, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || "Failed to generate preview");
      setPreview(j);
      setStep("preview");
    } catch (e2) {
      setErr(e2.message || "Preview failed");
    } finally {
      setBusy(false);
    }
  }

  function selectedGrant() {
    return selectedIdx >= 0 ? matches[selectedIdx] : null;
  }

  function saveForCheckout() {
    const payload = {
      org, category, budget, purpose, timeline,
      matches, selectedIdx,
      preview
    };
    saveSession("gf_intake", payload);
  }

  async function handlePay() {
    setErr("");
    setBusy(true);
    try {
      saveForCheckout();
      const r = await fetch(ENDPOINTS.checkout, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: org || "Tester",
          category,
          isTeacher: category === "Teacher / Individual Classroom"
        })
      });
      const j = await r.json();
      if (!j.ok || !j.url) throw new Error(j.error || "Stripe session failed");
      window.location.href = j.url; // redirect to Stripe checkout
    } catch (e2) {
      setErr(e2.message || "Payment init failed");
    } finally {
      setBusy(false);
    }
  }

  function downloadTxt() {
    const text = preview?.fullDraft
      || "Your draft is ready. (This is a simple text export for private testing.)";
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "GrantForgeUSA_Draft.txt";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  // ------- UI blocks -------
  const header = (
    <header style={{marginBottom: 16}}>
      <h1 style={{margin: 0}}>GrantForgeUSA</h1>
      <div style={{fontSize: 12, opacity: 0.85, marginTop: 6}}>
        “Unless the Lord builds the house, the builders labor in vain.” — Psalm 127:1
      </div>
      {health?.ok ? (
        <div style={{fontSize: 11, color: "#2e7d32", marginTop: 8}}>
          API: {API_BASE} — OK
        </div>
      ) : (
        <div style={{fontSize: 11, color: "#b71c1c", marginTop: 8}}>
          Checking API…
        </div>
      )}
    </header>
  );

  const errBox = err ? (
    <div style={{background:"#ffebee", color:"#b71c1c", padding:"8px 10px", borderRadius:8, marginTop:10}}>
      {err}
    </div>
  ) : null;

  if (step === "success") {
    return (
      <div style={{maxWidth: 860, margin: "32px auto", padding: "0 16px"}}>
        {header}
        <h2>Thank you for using GrantForgeUSA.</h2>
        <p>Your payment succeeded. Below is your unlocked draft.</p>

        {preview?.fullDraft ? (
          <>
            <pre style={{whiteSpace:"pre-wrap", background:"#f7f7f7", padding:16, borderRadius:10, border:"1px solid #eee"}}>
{preview.fullDraft}
            </pre>
            <div style={{display:"flex", gap:12, marginTop:12}}>
              <button onClick={downloadTxt}>Download TXT</button>
              <button onClick={() => { navigator.clipboard?.writeText(preview.fullDraft); }}>Copy Text</button>
              <button onClick={() => { clearSession("gf_intake"); window.location.href = "/"; }}>Back to Start</button>
            </div>
          </>
        ) : (
          <>
            <p>Your draft is ready. If you don’t see it, refresh this page. If the issue persists, contact support.</p>
            <button onClick={() => { window.location.href = "/"; }}>Return Home</button>
          </>
        )}
        <footer style={{marginTop: 28, fontSize: 12, opacity: 0.8}}>
          © {new Date().getFullYear()} GrantForgeUSA — All glory to God.
        </footer>
      </div>
    );
  }

  return (
    <div style={{maxWidth: 860, margin: "32px auto", padding: "0 16px"}}>
      {header}

      {step === "intake" && (
        <form onSubmit={handleStartIntake}>
          <div style={{display:"grid", gap:12}}>
            <label>
              <div>Your Organization</div>
              <input value={org} onChange={e=>setOrg(e.target.value)} placeholder="e.g., Community Hope Center" required />
            </label>

            <label>
              <div>Who Are You?</div>
              <select value={category} onChange={e=>setCategory(e.target.value)}>
                {CATS.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>

            <label>
              <div>Annual Budget (approx.)</div>
              <input value={budget} onChange={e=>setBudget(e.target.value)} placeholder="e.g., 450000" />
            </label>

            <label>
              <div>Purpose / Project Need</div>
              <input value={purpose} onChange={e=>setPurpose(e.target.value)} placeholder="e.g., after-school tutoring for 120 students" required />
            </label>

            <label>
              <div>Timeline (optional)</div>
              <input value={timeline} onChange={e=>setTimeline(e.target.value)} placeholder="e.g., launch by August" />
            </label>

            <div style={{background:"#f7f7f7", padding:"10px 12px", borderRadius:8}}>
              <div style={{fontSize:14}}>
                Intake, matches, and your short preview are <strong>free</strong>.
              </div>
              <div style={{fontSize:14, marginTop:4}}>
                If we draft your full proposal, the cost is <strong>{prettyUSD(fee)}</strong>.
              </div>
            </div>

            <div style={{display:"flex", gap:12, alignItems:"center"}}>
              <button type="submit" disabled={busy}>Start My Intake</button>
              {busy && <span>Working…</span>}
            </div>
          </div>
          {errBox}
        </form>
      )}

      {step === "matches" && (
        <div>
          <h2>Recommended Opportunities</h2>
          <p>Choose one opportunity to continue.</p>
          <ul style={{listStyle:"none", padding:0, margin:0}}>
            {matches.map((m, i) => (
              <li key={i} style={{border:"1px solid #eee", borderRadius:10, padding:12, marginBottom:10, background:"#fafafa"}}>
                <label style={{display:"flex", gap:12}}>
                  <input
                    type="radio"
                    name="grantpick"
                    checked={selectedIdx === i}
                    onChange={() => setSelectedIdx(i)}
                  />
                  <div>
                    <div style={{fontWeight:600}}>{m.title || "Grant Opportunity"}</div>
                    <div style={{fontSize:12, opacity:0.85}}>
                      {m.amount ? `${m.amount} — ` : ""}{m.deadline ? `Deadline ${m.deadline}` : "Rolling"} — Fit {m.fit || "Medium"}
                    </div>
                    {m.url && <div style={{fontSize:12}}><a href={m.url} target="_blank" rel="noreferrer">Program page</a></div>}
                  </div>
                </label>
              </li>
            ))}
          </ul>
          <div style={{display:"flex", gap:12, marginTop:8}}>
            <button disabled={selectedIdx < 0 || busy} onClick={handleGeneratePreview}>Generate Preview (Free)</button>
            <button onClick={()=>setStep("intake")} disabled={busy}>Back</button>
            {busy && <span>Working…</span>}
          </div>
          {errBox}
        </div>
      )}

      {step === "preview" && (
        <div>
          <h2>Preview (Free)</h2>
          <div style={{fontSize:13, marginBottom:8}}>
            Selected: <strong>{selectedGrant()?.title || "Grant"}</strong>
          </div>

          {/* Outline */}
          {preview?.outline ? (
            <div style={{border:"1px solid #eee", borderRadius:10, padding:12, background:"#fafafa"}}>
              {Object.entries(preview.outline).map(([k, v]) => (
                <section key={k} style={{marginBottom:10}}>
                  <h3 style={{margin:"8px 0"}}>{k}</h3>
                  {Array.isArray(v) ? (
                    <ul>{v.map((x, idx)=><li key={idx}>{x}</li>)}</ul>
                  ) : (
                    <p>{String(v)}</p>
                  )}
                </section>
              ))}
            </div>
          ) : (
            <p>Preview outline is loading…</p>
          )}

          {/* Fee + Stripe instructions */}
          <div style={{background:"#f7f7f7", padding:"10px 12px", borderRadius:8, marginTop:12}}>
            Drafting Fee: <strong>{prettyUSD(fee)}</strong>
            <div style={{fontSize:12, marginTop:6}}>
              Test card for checkout (Stripe Test Mode): <code>4242 4242 4242 4242</code> • any future expiry • any CVC/ZIP.
            </div>
          </div>

          <div style={{display:"flex", gap:12, marginTop:10}}>
            <button disabled={busy} onClick={handlePay}>Pay (Test) to Unlock Full Draft</button>
            <button onClick={()=>setStep("matches")} disabled={busy}>Back</button>
            {busy && <span>Working…</span>}
          </div>
          {errBox}
        </div>
      )}

      <footer style={{marginTop: 28, fontSize: 12, opacity: 0.8}}>
        © {new Date().getFullYear()} GrantForgeUSA — All glory to God.
      </footer>
    </div>
  );
}
