// src/App.jsx — v11 end-to-end UI (vertical/mobile-first)

import { useEffect, useMemo, useState } from "react";
import { API_BASE } from "./config";

const EP = {
  shortlist: `${API_BASE}/questionnaire`,
  preview: `${API_BASE}/preview`,
  checkout: `${API_BASE}/create-checkout-session`,
  session: `${API_BASE}/session`,
  download: `${API_BASE}/download`,
};

const CATEGORIES = [
  "Teacher (Classroom)",
  "School / District",
  "Small Nonprofit / Club",
  "Medium Nonprofit",
  "Large Nonprofit / Municipality",
  "Church / Faith Org",
  "Small Business",
  "Other",
];

const label = (t) => <label className="block text-sm font-medium mb-1">{t}</label>;

function Field({ labelText, children }) {
  return (
    <div className="mb-4">
      {label(labelText)}
      {children}
    </div>
  );
}

function Input(props) {
  return (
    <input
      {...props}
      className={
        "w-full rounded-md border px-3 py-2 text-sm outline-none focus:ring " +
        (props.className || "")
      }
    />
  );
}

function Textarea(props) {
  return (
    <textarea
      {...props}
      rows={3}
      className={
        "w-full rounded-md border px-3 py-2 text-sm outline-none focus:ring " +
        (props.className || "")
      }
    />
  );
}

function Button({ children, ...rest }) {
  return (
    <button
      {...rest}
      className={
        "inline-flex items-center justify-center rounded-md bg-sky-600 px-4 py-2 text-white text-sm font-semibold hover:bg-sky-700 disabled:opacity-60"
      }
    >
      {children}
    </button>
  );
}

function FitBadge({ fit }) {
  const tone =
    fit === "High" ? "bg-emerald-100 text-emerald-800" :
    fit === "Medium" ? "bg-amber-100 text-amber-800" :
    "bg-gray-100 text-gray-700";
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-semibold ${tone}`}>Fit {fit}</span>
  );
}

function Header() {
  return (
    <header className="mx-auto max-w-3xl px-4 py-6">
      <h1 className="text-3xl font-extrabold tracking-tight">GrantForgeUSA</h1>
      <p className="text-sm text-gray-600 mt-1">
        “Unless the Lord builds the house, the builders labor in vain.” — Psalm 127:1
      </p>
    </header>
  );
}

function Footer() {
  const year = new Date().getFullYear();
  return (
    <footer className="mx-auto max-w-3xl px-4 py-10 text-xs text-gray-500">
      <p>© {year} GrantForgeUSA</p>
      <p className="mt-1">
        This product uses AI to generate previews and draft language. Review and edit before any submission.
      </p>
    </footer>
  );
}

function ThanksPage() {
  const [status, setStatus] = useState({ loading: true, error: "", file: "", order_id: "" });

  useEffect(() => {
    const u = new URL(window.location.href);
    const sessionId = u.searchParams.get("session_id");
    if (!sessionId) {
      setStatus({ loading: false, error: "Missing session_id.", file: "", order_id: "" });
      return;
    }
    fetch(`${EP.session}?id=${encodeURIComponent(sessionId)}`)
      .then((r) => r.json())
      .then((j) => {
        if (!j.ok) throw new Error(j.error || "Unable to load session.");
        setStatus({ loading: false, error: "", file: j.file || "", order_id: j.order_id || "" });
      })
      .catch((e) => setStatus({ loading: false, error: e.message, file: "", order_id: "" }));
  }, []);

  const downloadHref = useMemo(() => {
    if (status.file) return `${EP.download}/${encodeURIComponent(status.file)}`;
    if (status.order_id) return `${EP.download}/${encodeURIComponent(status.order_id + ".pdf")}`;
    return "";
  }, [status]);

  return (
    <>
      <Header />
      <main className="mx-auto max-w-3xl px-4">
        <h2 className="text-xl font-semibold mb-4">Payment Success</h2>
        {status.loading ? (
          <p>Loading your draft…</p>
        ) : status.error ? (
          <p className="text-red-600">Error: {status.error}</p>
        ) : downloadHref ? (
          <p>
            <a className="text-sky-700 underline font-semibold" href={downloadHref}>
              Download Draft PDF
            </a>
          </p>
        ) : (
          <p>Your draft is being prepared. Please refresh this page in a moment.</p>
        )}
        <p className="mt-6 text-sm text-gray-600">
          Keep this link for your records. You can request edits before submission.
        </p>
      </main>
      <Footer />
    </>
  );
}

export default function App() {
  const isThanks = typeof window !== "undefined" && window.location.pathname === "/thanks";
  if (isThanks) return <ThanksPage />;

  const [form, setForm] = useState({
    organization: "",
    who: "",
    keywords: "",
    amount_requested: "",
    annual_budget: "",
    project_title: "",
    timeline: "",
    audience: "",
    notes: "",
  });

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [results, setResults] = useState([]); // shortlist grants
  const [price, setPrice] = useState(null);
  const [previews, setPreviews] = useState({}); // grant.title -> preview text
  const [paying, setPaying] = useState("");

  const onChange = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  function toNumber(v) {
    const n = parseFloat(String(v || "").replace(/[, ]/g, ""));
    return Number.isFinite(n) ? n : 0;
  }

  async function getShortlist() {
    setLoading(true);
    setError("");
    setResults([]);
    setPreviews({});
    try {
      const body = {
        organization: form.organization,
        who: form.who,
        keywords: form.keywords,
        amount_requested: toNumber(form.amount_requested),
        annual_budget: toNumber(form.annual_budget),
        project_title: form.project_title,
        timeline: form.timeline,
        audience: form.audience,
        notes: form.notes,
      };
      const r = await fetch(EP.shortlist, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || "Could not fetch recommendations.");
      setResults(j.results || []);
      setPrice(j.price ?? null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function getPreview(grant) {
    const key = grant.title;
    if (previews[key]) return; // already loaded
    try {
      const r = await fetch(EP.preview, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          form: {
            ...form,
            amount_requested: toNumber(form.amount_requested),
            annual_budget: toNumber(form.annual_budget),
          },
          grant,
        }),
      });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || "Preview failed.");
      setPreviews((p) => ({ ...p, [key]: j.preview || "" }));
    } catch (e) {
      setPreviews((p) => ({ ...p, [key]: `Preview unavailable. (${e.message})` }));
    }
  }

  async function payFor(grant) {
    setPaying(grant.title);
    setError("");
    try {
      const r = await fetch(EP.checkout, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          form: {
            ...form,
            amount_requested: toNumber(form.amount_requested),
            annual_budget: toNumber(form.annual_budget),
          },
          grant,
        }),
      });
      const j = await r.json();
      if (!j.ok || !j.url) throw new Error(j.error || "Checkout failed.");
      window.location.href = j.url; // Stripe redirect
    } catch (e) {
      setError(e.message);
    } finally {
      setPaying("");
    }
  }

  return (
    <>
      <Header />
      <main className="mx-auto max-w-3xl px-4">
        <section className="bg-white rounded-2xl shadow p-5 border">
          <h2 className="text-xl font-semibold mb-3">Tell us about your project (Free Intake)</h2>
          <p className="text-sm text-gray-600 mb-4">
            Intake is free. You only pay if you want a full custom draft.
          </p>

          <Field labelText="Organization">
            <Input placeholder="Your organization" value={form.organization} onChange={onChange("organization")} />
          </Field>

          <Field labelText="Who are you?">
            <select
              value={form.who}
              onChange={onChange("who")}
              className="w-full rounded-md border px-3 py-2 text-sm"
            >
              <option value="">Select a category</option>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </Field>

          <Field labelText="Keywords (comma separated)">
            <Input placeholder="e.g., STEM, food, youth" value={form.keywords} onChange={onChange("keywords")} />
          </Field>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field labelText="Amount Requested (USD)">
              <Input placeholder="e.g., 2500" value={form.amount_requested} onChange={onChange("amount_requested")} />
            </Field>
            <Field labelText="Annual Budget (USD)">
              <Input placeholder="e.g., 60000" value={form.annual_budget} onChange={onChange("annual_budget")} />
            </Field>
          </div>

          <Field labelText="Project Title">
            <Input placeholder="Short name of the project" value={form.project_title} onChange={onChange("project_title")} />
          </Field>

          <Field labelText="Timeline">
            <Input placeholder="What do you need & when?" value={form.timeline} onChange={onChange("timeline")} />
          </Field>

          <Field labelText="Audience / Who benefits?">
            <Input placeholder="Who is served (students, vets, families…)" value={form.audience} onChange={onChange("audience")} />
          </Field>

          <Field labelText="Notes (optional)">
            <Textarea placeholder="Anything else reviewers should know" value={form.notes} onChange={onChange("notes")} />
          </Field>

          <div className="mt-2">
            <Button onClick={getShortlist} disabled={loading}>
              {loading ? "Finding matches…" : "See Recommendations"}
            </Button>
          </div>

          {error && <p className="mt-3 text-sm text-red-600">Error: {error}</p>}
        </section>

        {!!results.length && (
          <section className="mt-8">
            <h3 className="text-lg font-semibold mb-3">Recommended Opportunities</h3>
            <ul className="space-y-6">
              {results.map((g) => (
                <li key={g.title} className="border rounded-xl p-4">
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                    <div>
                      <a href={g.program_url || "#"} target="_blank" rel="noreferrer" className="font-semibold underline">
                        {g.title}
                      </a>
                      <div className="text-sm text-gray-600 mt-1">
                        ${g.min_amount?.toLocaleString?.() ?? g.min_amount} — ${g.max_amount?.toLocaleString?.() ?? g.max_amount}
                        {"  "} • Deadline {g.deadline || "TBD"} {"  "} • <FitBadge fit={g.fit} />
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        className="text-sky-700 underline text-sm"
                        onClick={() => getPreview(g)}
                      >
                        Preview (Free)
                      </button>
                      <Button onClick={() => payFor(g)} disabled={paying === g.title}>
                        {paying === g.title ? "Opening checkout…" : `Draft this (Pay ${price ? `$${price.toFixed(2)}` : ""})`}
                      </Button>
                    </div>
                  </div>
                  {previews[g.title] && (
                    <p className="mt-3 text-sm text-gray-800">{previews[g.title]}</p>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}
      </main>
      <Footer />
    </>
  );
}
