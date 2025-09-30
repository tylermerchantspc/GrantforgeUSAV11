// src/App.jsx
import React, { useState } from "react";
import "./App.css";
import CONFIG from "./config";
import { jsPDF } from "jspdf";

const { API_BASE } = CONFIG;

function App() {
  // form
  const [org, setOrg] = useState("");
  const [keywords, setKeywords] = useState("");

  // data
  const [intakeId, setIntakeId] = useState(null);
  const [grants, setGrants] = useState([]);
  const [draft, setDraft] = useState(null);

  // ui
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [payFor, setPayFor] = useState(null); // {id, title} or null
  const [paidDraftIds, setPaidDraftIds] = useState(new Set()); // visual tag only

  // ---------- helpers ----------
  const api = async (path, body) => {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : "{}",
    });
    if (!res.ok) throw new Error(`API ${path} failed (${res.status})`);
    return await res.json();
  };

  const findGrants = async () => {
    setError("");
    setDraft(null);
    setGrants([]);
    setLoading(true);
    try {
      // 1) create questionnaire (gets intake_id we reuse for drafts)
      const q = await api("/questionnaire", {
        name: org || "Your Organization",
        keywords: keywords || "grants",
      });
      // backend returns: { ok, ts, draft? } but we designed it to create a doc and
      // hand back an intake id in Firestore via /questionnaire. Some versions return
      // only ok/ts. To keep flow stable, we also compute an intake key in backend
      // when drafting. If q has no id, we'll keep using null (backend tolerates).
      setIntakeId(q.id || q.intake_id || null);

      // 2) fetch grants
      const g = await api("/find-grants", { keywords });
      setGrants(g.top || g.items || []);
    } catch (e) {
      console.error(e);
      setError(e.message || "Failed to fetch");
    } finally {
      setLoading(false);
    }
  };

  const createDraft = async (g) => {
    setError("");
    setLoading(true);
    try {
      const d = await api("/draft", {
        intake_id: intakeId,
        organization: org || "Your Organization",
        grant: {
          id: g.id,
          title: g.title,
          agency: g.agency,
          url: g.url || "https://example.com",
        },
      });
      // expected: { ok: true, draft_id, preview }
      setDraft({
        id: d.draft_id || d.id,
        preview: d.preview || "",
        grant: g,
      });
    } catch (e) {
      console.error(e);
      setError(e.message || "Failed to create draft");
    } finally {
      setLoading(false);
    }
  };

  const exportPDF = () => {
    if (!draft) return;
    const doc = new jsPDF({ unit: "pt", format: "letter" });
    const left = 60;
    const top = 72;
    const width = 475;

    const title = draft.grant?.title || "Grant Opportunity";
    const orgName = org || "Your Organization";
    const body =
      draft.preview ||
      `Dear Review Committee,

This is a generated placeholder draft for ${orgName} applying to: ${title}.

[Insert problem statement, goals, outcomes, budget summary.]

Sincerely,
${orgName}`;

    doc.setFont("helvetica", "bold");
    doc.setFontSize(18);
    doc.text("GrantForgeUSA – Draft Letter", left, top);

    doc.setFont("helvetica", "normal");
    doc.setFontSize(12);
    const lines = doc.splitTextToSize(body, width);
    doc.text(lines, left, top + 32);

    const filename =
      `GFUSA_${(title || "draft").slice(0, 40).replace(/\s+/g, "_")}_${(draft.id || "doc").slice(0, 8)}.pdf`;
    doc.save(filename);
  };

  const openPay = (gOrDraft) => {
    const id = gOrDraft.id || gOrDraft.grant?.id || "unknown";
    const title = gOrDraft.title || gOrDraft.grant?.title || "Draft";
    setPayFor({ id, title });
  };

  const confirmPay = () => {
    if (payFor?.id) {
      const next = new Set(paidDraftIds);
      next.add(payFor.id);
      setPaidDraftIds(next);
    }
    setPayFor(null);
  };

  // ---------- render ----------
  return (
    <div className="wrap">
      <header>
        <h1>GrantForgeUSA</h1>
        <p className="sub">
          Enter your organization and a keyword (e.g., “veterans”, “education”), then click{" "}
          <strong>Find Grants</strong>. Click <strong>Draft</strong> to generate a placeholder letter.
        </p>
      </header>

      <div className="box">
        <div className="row">
          <input
            value={org}
            onChange={(e) => setOrg(e.target.value)}
            placeholder="Your Organization"
          />
          <input
            value={keywords}
            onChange={(e) => setKeywords(e.target.value)}
            placeholder="Keywords (e.g., education grants)"
          />
          <button className="btn primary" onClick={findGrants} disabled={loading}>
            {loading ? "Working…" : "Find Grants"}
          </button>
        </div>

        {error && <div className="error">Error: {error}</div>}

        {grants.length > 0 && (
          <>
            <h2>Top Grants</h2>
            <ul className="list">
              {grants.map((g) => {
                const id = g.id || g.title;
                const isPaid = paidDraftIds.has(id);
                return (
                  <li key={id} className="grant">
                    <h3>
                      <a href={g.url || "https://example.com"} target="_blank" rel="noreferrer">
                        {g.title || "Grant Opportunity"}
                      </a>{" "}
                      — <span className="agency">{g.agency || "Sample Agency"}</span>
                    </h3>
                    <div className="meta">
                      Score: {typeof g.score === "number" ? g.score.toFixed(2) : "N/A"}{" "}
                      | Deadline: {g.deadline || "N/A"}
                      {isPaid && <span className="paid">PAID</span>}
                    </div>

                    <div className="actions">
                      <a
                        className="link"
                        href={g.url || "https://example.com"}
                        target="_blank"
                        rel="noreferrer"
                      >
                        View Grant
                      </a>
                      <button className="btn secondary" onClick={() => createDraft(g)}>
                        Draft
                      </button>
                      <button className="btn ghost" onClick={() => openPay(g)}>
                        Payment
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </>
        )}

        {draft && (
          <div className="draft-box">
            <h3>Draft Created</h3>
            <div className="kv">
              <span className="k">Draft ID:</span>
              <span className="v mono">{draft.id}</span>
            </div>
            <div className="kv">
              <span className="k">Preview:</span>
              <span className="v">{draft.preview || "(no preview provided)"}</span>
            </div>
            <div className="actions">
              <button className="btn primary" onClick={exportPDF}>
                Download PDF
              </button>
              <button className="btn ghost" onClick={() => openPay(draft)}>
                Payment
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Payment Modal (fake checkout) */}
      {payFor && (
        <Modal onClose={() => setPayFor(null)} title="Test Payment">
          <p style={{ marginTop: 0 }}>
            This is a <strong>test-only</strong> payment window. No real money is charged.
          </p>
          <p>
            Item: <strong>{payFor.title}</strong>
          </p>
          <div className="row">
            <button className="btn secondary" onClick={confirmPay}>
              Mark as Paid
            </button>
            <button className="btn ghost" onClick={() => setPayFor(null)}>
              Cancel
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

// ---------- tiny modal component ----------
function Modal({ title, children, onClose }) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="x" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

export default App;