// src/App.jsx — v1.1 Intake → shortlist (free preview) → pay → finalize link
import { useEffect, useMemo, useState } from "react";
import { findGrants, getPreview, startCheckout, finalizeDraft } from "./fetcher";
import { API_BASE } from "./config";

const WHOS = [
  "Teacher (Classroom)",
  "School / District",
  "501(c)(3) Nonprofit",
  "Church / Faith-Based",
  "Small Business",
  "City / Municipality",
  "Club / Booster",
  "Other",
];

function useQuery() {
  return useMemo(() => new URLSearchParams(window.location.search), []);
}

function Label({ children }) {
  return <label className="block text-sm font-medium text-slate-700 mb-1">{children}</label>;
}

function Input(props) {
  return (
    <input
      {...props}
      className={`w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-sky-500 ${props.className||""}`}
    />
  );
}

function Select({ value, onChange }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500"
    >
      <option value="">Select a category</option>
      {WHOS.map((w) => (
        <option key={w} value={w}>{w}</option>
      ))}
    </select>
  );
}

function Card({ children }) {
  return <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">{children}</div>;
}

function Shell({ children }) {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-3xl px-4 py-6">
          <h1 className="text-3xl font-bold text-slate-900">GrantForgeUSA</h1>
          <p className="mt-1 text-slate-500 text-sm">
            “Unless the Lord builds the house, the builders labor in vain.” — Psalm 127:1
          </p>
          <p className="mt-1 text-slate-400 text-xs">API: {API_BASE}</p>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-6">{children}</main>
      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto max-w-3xl px-4 py-6 text-xs text-slate-500 space-y-1">
          <div>© {new Date().getFullYear()} GrantForgeUSA</div>
          <div>
            This product uses AI to generate previews and draft language. Review and edit before any submission.
          </div>
        </div>
      </footer>
    </div>
  );
}

export default function App() {
  const query = useQuery();
  const sessionId = query.get("session_id");
  const isThanks = window.location.pathname === "/thanks";
  const isCancel = window.location.pathname === "/cancel";

  if (isThanks) return <ThanksView sessionId={sessionId} />;
  if (isCancel) return (
    <Shell>
      <Card><p className="text-slate-700">Payment cancelled. You can return to your recommendations to try again.</p></Card>
    </Shell>
  );
  return <IntakeFlow />;
}

function IntakeFlow() {
  const [intake, setIntake] = useState({
    organization: "",
    who: "",
    keywords: "",
    amount: "",
    budget: "",
    title: "",
    timeline: "",
    audience: "",
    notes: "",
  });

  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState([]);
  const [error, setError] = useState("");

  const onChange = (k, v) => setIntake((s) => ({ ...s, [k]: v }));

  async function onSeeRecs() {
    setLoading(true); setError("");
    try {
      const r = await findGrants(intake);
      if (!r.ok) throw new Error(r.error || "Failed");
      setResults(r.results || []);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      setError("Could not fetch recommendations.");
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Shell>
      <Card>
        <h2 className="text-xl font-semibold text-slate-900">Tell us about your project (Free Intake)</h2>
        <p className="text-slate-500 text-sm mt-1">
          Intake is free. You only pay if you want a full custom draft.
        </p>

        <div className="mt-4 grid grid-cols-1 gap-4">
          <div>
            <Label>Organization</Label>
            <Input placeholder="Your Organization" value={intake.organization} onChange={(e)=>onChange("organization", e.target.value)} />
          </div>

          <div>
            <Label>Who are you?</Label>
            <Select value={intake.who} onChange={(v)=>onChange("who", v)} />
          </div>

          <div>
            <Label>Keywords (comma separated)</Label>
            <Input placeholder="e.g., STEM, food, youth" value={intake.keywords} onChange={(e)=>onChange("keywords", e.target.value)} />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <Label>Amount Requested (USD)</Label>
              <Input type="number" placeholder="e.g., 2500" value={intake.amount} onChange={(e)=>onChange("amount", e.target.value)} />
            </div>
            <div>
              <Label>Annual Budget (USD)</Label>
              <Input type="number" placeholder="e.g., 60000" value={intake.budget} onChange={(e)=>onChange("budget", e.target.value)} />
            </div>
          </div>

          <div>
            <Label>Project Title</Label>
            <Input placeholder="Short name of the project" value={intake.title} onChange={(e)=>onChange("title", e.target.value)} />
          </div>

          <div>
            <Label>Timeline</Label>
            <Input placeholder="What do you need & when?" value={intake.timeline} onChange={(e)=>onChange("timeline", e.target.value)} />
          </div>

          <div>
            <Label>Audience / Who benefits?</Label>
            <Input placeholder="Who is served (students, veterans, youth)?" value={intake.audience} onChange={(e)=>onChange("audience", e.target.value)} />
          </div>

          <div>
            <Label>Notes (optional)</Label>
            <Input placeholder="Anything else reviewers should know" value={intake.notes} onChange={(e)=>onChange("notes", e.target.value)} />
          </div>

          <button
            onClick={onSeeRecs}
            disabled={loading}
            className="mt-2 inline-flex items-center justify-center rounded-md bg-sky-600 px-4 py-2 font-medium text-white hover:bg-sky-700 disabled:opacity-50"
          >
            {loading ? "Finding options..." : "See Recommendations"}
          </button>

          {error && <p className="text-red-600 text-sm">{error}</p>}
        </div>
      </Card>

      {results.length > 0 && (
        <div className="mt-6 space-y-4">
          <h3 className="text-lg font-semibold text-slate-900">Recommended Opportunities</h3>
          {results.map((g) => (
            <GrantCard key={g.id} grant={g} intake={intake} />
          ))}
        </div>
      )}
    </Shell>
  );
}

function GrantCard({ grant, intake }) {
  const [preview, setPreview] = useState("");
  const [loadingPrev, setLoadingPrev] = useState(false);
  const [loadingPay, setLoadingPay] = useState(false);

  const humanPrice = (() => {
    const b = parseFloat(intake.budget || 0);
    if ((intake.who || "").toLowerCase().includes("teacher")) return 9.99;
    if (b <= 500000) return 49.99;
    if (b <= 2000000) return 99.99;
    return 199.99;
  })();

  async function onPreview() {
    setLoadingPrev(true);
    try {
      const r = await getPreview(grant.id, intake);
      if (r.ok) setPreview(r.preview);
    } finally {
      setLoadingPrev(false);
    }
  }

  async function onDraftThis() {
    setLoadingPay(true);
    try {
      const r = await startCheckout({ grantId: grant.id, intake, category: intake.who });
      if (r.ok && r.url) {
        window.location = r.url;
      }
    } finally {
      setLoadingPay(false);
    }
  }

  return (
    <Card>
      <div className="flex items-start justify-between gap-4">
        <div>
          <a href="#" className="font-semibold text-sky-700 hover:underline">{grant.title}</a>
          <div className="text-sm text-slate-500">
            {grant.amount} — Deadline {grant.deadline} — Fit {grant.fit}
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onPreview}
            disabled={loadingPrev}
            className="rounded-md border border-slate-300 px-3 py-2 text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {loadingPrev ? "Loading..." : "Preview (Free)"}
          </button>
          <button
            onClick={onDraftThis}
            disabled={loadingPay}
            className="rounded-md bg-emerald-600 px-3 py-2 text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {loadingPay ? "Opening checkout..." : `Draft this (Pay $${humanPrice.toFixed(2)})`}
          </button>
        </div>
      </div>
      {preview && <p className="mt-3 text-slate-700">{preview}</p>}
    </Card>
  );
}

function ThanksView({ sessionId }) {
  const [state, setState] = useState({ loading: true, url: "", error: "" });

  useEffect(() => {
    let mounted = true;
    async function run() {
      try {
        const r = await finalizeDraft(sessionId || "");
        if (!mounted) return;
        if (r.ok) setState({ loading: false, url: r.download_url, error: "" });
        else setState({ loading: false, url: "", error: r.error || "Finalize failed" });
      } catch (e) {
        if (!mounted) return;
        setState({ loading: false, url: "", error: "Finalize failed" });
      }
    }
    if (sessionId) run();
    else setState({ loading: false, url: "", error: "Missing session_id" });
    return () => { mounted = False };
  }, [sessionId]);

  return (
    <Shell>
      <Card>
        <h2 className="text-xl font-semibold text-slate-900">Payment Success</h2>
        {state.loading && <p className="mt-2 text-slate-700">Creating your full draft…</p>}
        {!state.loading && state.error && <p className="mt-2 text-red-600">{state.error}</p>}
        {!state.loading && state.url && (
          <div className="mt-3">
            <a
              className="inline-flex items-center rounded-md bg-sky-600 px-4 py-2 font-medium text-white hover:bg-sky-700"
              href={state.url}
              target="_blank" rel="noreferrer"
            >
              Download Draft PDF
            </a>
            <p className="mt-2 text-sm text-slate-500">
              Keep this link for your records. You can request edits before submission.
            </p>
          </div>
        )}
      </Card>
    </Shell>
  );
}
