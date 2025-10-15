// src/App.jsx — v1.1 minimal working UI
import { useState } from "react";
import { API_BASE } from "./config";
import { apiHealth, findGrants, getDraft } from "./fetcher";

export default function App() {
  const [org, setOrg] = useState("");
  const [kw, setKw] = useState("");
  const [status, setStatus] = useState("");
  const [results, setResults] = useState([]);

  async function handleHealth() {
    setStatus("Checking backend…");
    try {
      const h = await apiHealth();
      setStatus(`Backend OK • ${h.frontendUrl || ""} • ${new Date().toLocaleTimeString()}`);
    } catch (e) {
      setStatus("Health check failed");
      console.error(e);
    }
  }

  async function handleFind() {
    setStatus("Finding grants…");
    setResults([]);
    try {
      const data = await findGrants(org || "Your Organization", kw || "community");
      setResults(data.results || []);
      setStatus(`Found ${data.results?.length || 0} item(s)`);
    } catch (e) {
      setStatus("Error: Failed to fetch");
      console.error(e);
    }
  }

  async function handleDraft() {
    setStatus("Making outline…");
    try {
      const d = await getDraft(org || "Your Organization", kw || "community");
      alert("Draft outline ready (preview only). Check console for details.");
      console.log("Draft outline", d);
      setStatus("Outline generated");
    } catch (e) {
      setStatus("Draft error");
      console.error(e);
    }
  }

  return (
    <div style={{ maxWidth: 720, margin: "40px auto", fontFamily: "system-ui" }}>
      <h1>GrantForgeUSA</h1>
      <p style={{ color: "#555" }}>
        API: <code>{API_BASE}</code>
      </p>

      <div style={{ display: "grid", gap: 8 }}>
        <input placeholder="Your Organization" value={org} onChange={e=>setOrg(e.target.value)} />
        <input placeholder="Keywords (e.g., veterans, education)" value={kw} onChange={e=>setKw(e.target.value)} />
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={handleFind}>Find Grants</button>
          <button onClick={handleDraft}>Draft</button>
          <button onClick={handleHealth}>Check Health</button>
        </div>
      </div>

      <p style={{ marginTop: 12 }}>{status}</p>

      <ul>
        {results.map((g, i) => (
          <li key={i} style={{ margin: "8px 0" }}>
            <strong>{g.title}</strong> — {g.amount} — Deadline {g.deadline} — Fit {g.fit}
          </li>
        ))}
      </ul>
    </div>
  );
}
