"use client";

import { useCallback, useEffect, useState } from "react";
import {
  API, call,
  type Alternatives, type CancelPrep, type Health, type MissingItem, type Subscription, type Summary, type TraceStep,
} from "./api";

const money = (n: number) => `$${n.toFixed(2)}`;

type Panel =
  | { id: string; kind: "cancel"; data: CancelPrep }
  | { id: string; kind: "cheaper"; data: Alternatives }
  | null;

export default function Home() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [subs, setSubs] = useState<Subscription[]>([]);
  const [trace, setTrace] = useState<TraceStep[]>([]);
  const [missing, setMissing] = useState<MissingItem[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [panel, setPanel] = useState<Panel>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, list, t, m, h] = await Promise.all([
        call<Summary>("/api/summary"),
        call<Subscription[]>("/api/subscriptions"),
        call<TraceStep[]>("/api/trace"),
        call<MissingItem[]>("/api/missing"),
        call<Health>("/api/health"),
      ]);
      setSummary(s); setSubs(list); setTrace(t); setMissing(m); setHealth(h); setError(null);
    } catch (e) {
      setError(`Can't reach the backend at ${API}. Start it with: cd backend && .venv\\Scripts\\uvicorn clawback.main:app --reload`);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function post(path: string, body?: unknown) {
    try {
      const out = await call<unknown>(path, {
        method: "POST",
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      await load();
      return out;
    } catch (e) {
      setNotice((e as Error).message);
      return null;
    }
  }

  async function openCancel(id: string) {
    const data = (await post(`/api/subscriptions/${id}/cancel-prep`)) as CancelPrep | null;
    if (data) setPanel({ id, kind: "cancel", data });
  }

  async function openCheaper(id: string) {
    try {
      const data = await call<Alternatives>(`/api/subscriptions/${id}/alternatives`);
      setPanel({ id, kind: "cheaper", data });
      await load();
    } catch (e) { setNotice((e as Error).message); }
  }

  async function tryMissing(path: string) {
    try { await call(path); } catch (e) { setNotice((e as Error).message); }
  }

  async function upload(file: File) {
    const form = new FormData();
    form.append("file", file);
    try {
      const out = await call<{ added_transactions: number }>("/api/ingest/statement", { method: "POST", body: form });
      setNotice(`Added ${out.added_transactions} transactions from ${file.name}.`);
      await load();
    } catch (e) { setNotice((e as Error).message); }
  }

  const p0 = missing.filter((m) => m.priority === "P0").length;

  return (
    <main>
      <header className="top">
        <div>
          <h1>ClawBack</h1>
          <p className="muted">Finds the subscriptions you pay for but don&apos;t use, then helps you cancel or pay less.</p>
        </div>
        <div className="actions">
          <button onClick={() => tryMissing("/api/connect/gmail")} title="MISSING: Gmail OAuth">Connect Gmail <span className="tag missing">missing</span></button>
          <button onClick={() => tryMissing("/api/connect/plaid")} title="MISSING: Plaid Link">Connect bank <span className="tag missing">missing</span></button>
          <label className="button">
            Upload statement CSV
            <input type="file" accept=".csv" hidden onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          </label>
          <button onClick={() => post("/api/sync")}>Re-run</button>
          <button onClick={() => { setPanel(null); post("/api/demo/seed"); }}>Reset demo</button>
        </div>
      </header>

      {error && <div className="banner error">{error}</div>}
      {notice && <div className="banner notice" onClick={() => setNotice(null)}>{notice} <span className="muted">(click to dismiss)</span></div>}

      <details className="banner missingbox">
        <summary>
          <strong>Prototype.</strong> {missing.length} pieces are MISSING ({p0} needed for the demo). Showing demo data for one fake user.
        </summary>
        <table>
          <thead><tr><th>Priority</th><th>Area</th><th>What&apos;s missing</th><th>Where</th></tr></thead>
          <tbody>
            {[...missing].sort((a, b) => a.priority.localeCompare(b.priority)).map((m) => (
              <tr key={m.id}><td>{m.priority}</td><td>{m.area}</td><td>{m.what}{m.note && <div className="muted small">{m.note}</div>}</td><td><code>{m.where}</code></td></tr>
            ))}
          </tbody>
        </table>
        {health && (
          <p className="small">Connected services: {Object.entries(health.integrations).map(([k, v]) => `${k} ${v ? "yes" : "NO"}`).join(" · ")}</p>
        )}
      </details>

      {summary && (
        <section className="stats">
          <div><span className="muted">Subscriptions</span><b>{money(summary.monthly_total)}/mo</b><span className="small muted">{summary.subscriptions} found</span></div>
          <div><span className="muted">You could save</span><b className="good">{money(summary.potential_monthly_savings)}/mo</b><span className="small muted">{summary.flagged} flagged</span></div>
          <div><span className="muted">Recovered so far</span><b>{money(summary.recovered_total)}</b><span className="small missingtext">{summary.recovered_note}</span></div>
        </section>
      )}

      <section className="list">
        {subs.map((s) => (
          <article key={s.id} className={`card ${s.flags.some((f) => f.severity === "high") ? "hot" : ""}`}>
            <div className="row">
              <div>
                <h2>{s.merchant} {s.status !== "active" && <span className="tag">{s.status.replace("_", " ")}</span>}</h2>
                <p className="muted small">
                  {money(s.monthly_cost)}/mo{s.cadence ? ` · ${s.cadence}` : ""}
                  {s.next_expected ? ` · next charge ${s.next_expected}` : ""}
                  {` · from ${s.detected_from.join(" + ")}`}
                </p>
              </div>
              <div className={`usage ${s.usage.level}`}>usage: {s.usage.level}</div>
            </div>

            {s.flags.length > 0 && (
              <ul className="flags">
                {s.flags.map((f, i) => (
                  <li key={i} className={f.severity}>{f.message}{f.monthly_savings > 0 && <b> Save {money(f.monthly_savings)}/mo.</b>}</li>
                ))}
              </ul>
            )}

            <details className="small">
              <summary className="muted">Evidence</summary>
              <ul>{s.usage.evidence.map((e, i) => <li key={i}>{e}</li>)}</ul>
            </details>

            <div className="actions">
              <span className="muted small">Used it this month?</span>
              <button onClick={() => post(`/api/subscriptions/${s.id}/checkin`, { used: true })}>Yes</button>
              <button onClick={() => post(`/api/subscriptions/${s.id}/checkin`, { used: false })}>No</button>
              <span className="spacer" />
              <button onClick={() => post(`/api/subscriptions/${s.id}/keep`)}>Keep</button>
              <button onClick={() => openCheaper(s.id)}>Find cheaper</button>
              <button className="primary" onClick={() => openCancel(s.id)}>Prepare cancel</button>
            </div>

            {panel?.id === s.id && panel.kind === "cancel" && (
              <div className="panel">
                <h3>Cancel {panel.data.merchant}: saves {money(panel.data.you_save_per_month)}/mo{panel.data.next_charge && `, cancel before ${panel.data.next_charge}`}</h3>
                <p className="small muted">ClawBack never cancels or sends anything for you. You do the final click.</p>
                {panel.data.links.length > 0 && (
                  <ul>{panel.data.links.map((l) => (
                    <li key={l.url}><a href={l.url} target="_blank" rel="noreferrer">{l.label}</a> {l.verified ? <span className="tag">verified</span> : <span className="tag missing">unverified</span>}</li>
                  ))}</ul>
                )}
                <ol>{panel.data.steps.map((st, i) => <li key={i}>{st}</li>)}</ol>
                <p><b>Email:</b> {panel.data.email.subject}</p>
                <pre>{panel.data.email.body}</pre>
                <p className="missingtext small">{panel.data.email.status}</p>
                {panel.data.missing.map((m, i) => <p key={i} className="missingtext small">{m}</p>)}
                <button onClick={() => setPanel(null)}>Close</button>
              </div>
            )}

            {panel?.id === s.id && panel.kind === "cheaper" && (
              <div className="panel">
                <h3>Cheaper ways to get what you use</h3>
                {panel.data.options.length > 0 && (
                  <ul>{panel.data.options.map((o, i) => (
                    <li key={i}><b>{o.option}</b>{o.monthly_price != null && ` · ${money(o.monthly_price)}/mo`}: {o.why} <a href={o.source_url} target="_blank" rel="noreferrer">source</a></li>
                  ))}</ul>
                )}
                <ul>{panel.data.hints.map((h, i) => <li key={i}>{h}</li>)}</ul>
                {panel.data.missing.map((m, i) => <p key={i} className="missingtext small">{m}</p>)}
                <button onClick={() => setPanel(null)}>Close</button>
              </div>
            )}
          </article>
        ))}
      </section>

      <section>
        <h2>What ran (model trace)</h2>
        <p className="muted small">Every step records which engine ran it, how long it took and what it cost. Rows marked &quot;missing&quot; are stand-ins. &quot;fallback&quot; rows are where a backup model took over.</p>
        <div className="tablewrap">
          <table>
            <thead><tr><th>Stage</th><th>Tier</th><th>Engine</th><th>Status</th><th>ms</th><th>Tokens in/out</th><th>Cost</th><th>Note</th></tr></thead>
            <tbody>
              {trace.map((t, i) => (
                <tr key={i} className={t.status}>
                  <td>{t.stage}</td><td>{t.tier || "—"}</td><td><code>{t.engine}</code></td><td>{t.status}</td><td>{t.ms.toFixed(1)}</td>
                  <td>{t.input_tokens}/{t.output_tokens}{t.reasoning_tokens > 0 ? ` (+${t.reasoning_tokens} thinking)` : ""}</td><td>${t.cost_usd.toFixed(5)}</td><td>{t.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <footer className="muted small">MISSING: login, real data connections, Gmail drafts and confirmed savings. See STATUS.md.</footer>
    </main>
  );
}
