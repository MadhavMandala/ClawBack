"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  API, call,
  type ActionPrep, type Alerts, type Alternatives, type CancelPrep, type Connection, type Connections,
  type Finding, type Recovered, type Subscription, type Summary, type TraceStep,
} from "../api";
import { bankNotice, connectBank as openPlaid, connectEmail as openEmailSignIn } from "../connect";
import { groupOf, humanDates, money, reclaimable, shortDate, type GroupKey } from "../format";
import FindingRow from "../components/FindingRow";
import SiteNav from "../components/SiteNav";
import Donut from "../components/Donut";
import SubscriptionRow, { PrimaryAction, type RowPanel } from "../components/SubscriptionRow";
import { Check, Chevron, Close } from "../components/icons";
import "./dashboard.css";

type Notice = { tone: "info" | "error" | "missing"; text: string } | null;

const GROUPS: { key: GroupKey; title: string; short: string }[] = [
  { key: "decide", title: "Subscriptions to decide on", short: "To decide" },
  { key: "bills", title: "Bills you could lower", short: "Bills" },
  { key: "check", title: "Worth a look", short: "Worth a look" },
  { key: "fine", title: "Looks fine", short: "Looks fine" },
  { key: "cancelled", title: "Cancelled", short: "Cancelled" },
];

const GUIDE_KEY = "clawback.guide.done";

export default function Dashboard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [subs, setSubs] = useState<Subscription[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [findOpen, setFindOpen] = useState<string | null>(null);
  const [findPrep, setFindPrep] = useState<{ id: string; a: ActionPrep } | null>(null);
  const [trace, setTrace] = useState<TraceStep[]>([]);
  const [conns, setConns] = useState<Connections | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [panel, setPanel] = useState<{ id: string; p: RowPanel } | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [intro, setIntro] = useState(true);
  const [ready, setReady] = useState(false);
  const [alerts, setAlerts] = useState<Alerts | null>(null);
  const [recovered, setRecovered] = useState<Recovered | null>(null);
  const [guide, setGuide] = useState(false);
  const [slice, setSlice] = useState<string | null>(null);
  const [connectOpen, setConnectOpen] = useState(false);
  const loaded = useRef(false);

  // The first-visit guide: three lines, shown once per browser.
  useEffect(() => {
    try { setGuide(!window.localStorage.getItem(GUIDE_KEY)); } catch { setGuide(true); }
  }, []);
  function closeGuide() {
    setGuide(false);
    try { window.localStorage.setItem(GUIDE_KEY, "1"); } catch { /* shown again next visit */ }
  }

  // The page was empty when the browser tried to jump to #anchor; jump once everything has rendered.
  useEffect(() => {
    if (ready && window.location.hash) document.querySelector(window.location.hash)?.scrollIntoView();
  }, [ready]);

  const load = useCallback(async () => {
    try {
      const [s, list, t] = await Promise.all([
        call<Summary>("/api/summary"),
        call<Subscription[]>("/api/subscriptions"),
        call<TraceStep[]>("/api/trace"),
      ]);
      setSummary(s); setSubs(list); setTrace(t);
      setFindings(await call<Finding[]>("/api/findings").catch(() => []));
      setConns(await call<Connections>("/api/connections").catch(() => null));
      setAlerts(await call<Alerts>("/api/alerts").catch(() => null));
      setRecovered(await call<Recovered>("/api/recovered").catch(() => null));
      if (!loaded.current) {
        loaded.current = true;
        setTimeout(() => setIntro(false), 1600); // the highlighter pass runs once, on first load
        setReady(true);
      }
    } catch {
      setNotice({ tone: "error", text: `Can't reach the ClawBack server at ${API}. Start it from the backend folder with: .venv\\Scripts\\python -m uvicorn clawback.main:app --port 8000` });
    }
  }, []);

  useEffect(() => {
    load();
    // Coming back from the email sign-in lands here with ?connected=email or ?connect_error=...
    const q = new URLSearchParams(window.location.search);
    if (q.get("connected") === "email") setNotice({ tone: "info", text: "Email connected. ClawBack read your recent receipts and billing emails." });
    if (q.get("connect_error")) setNotice({ tone: "error", text: `Couldn't connect: ${q.get("connect_error")}` });
    if (q.toString()) window.history.replaceState(null, "", window.location.pathname + window.location.hash);
  }, [load]);

  async function act<T>(key: string, path: string, init?: RequestInit): Promise<T | null> {
    setBusy(key);
    try {
      const out = await call<T>(path, init);
      await load();
      return out;
    } catch (e) {
      const text = (e as Error).message;
      setNotice({ tone: /^MISSING/i.test(text) ? "missing" : "error", text });
      return null;
    } finally {
      setBusy(null);
    }
  }

  const post = <T,>(key: string, path: string, body?: unknown) =>
    act<T>(key, path, {
      method: "POST",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });

  async function connectEmail() {
    setBusy("email");
    try {
      await openEmailSignIn();
    } catch (e) {
      setNotice({ tone: /^MISSING/i.test((e as Error).message) ? "missing" : "error", text: (e as Error).message });
      setBusy(null);
    }
  }

  async function connectBank() {
    setBusy("plaid");
    try {
      const r = await openPlaid();
      if (r) { setNotice({ tone: "info", text: bankNotice(r) }); await load(); }
    } catch (e) {
      setNotice({ tone: /^MISSING/i.test((e as Error).message) ? "missing" : "error", text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  async function seenAlerts() {
    const out = await post<{ unseen: number }>("alerts", "/api/alerts/seen");
    if (out) setAlerts((a) => (a ? { alerts: a.alerts.map((x) => ({ ...x, seen: true })), unseen: 0 } : a));
  }

  async function upload(file: File) {
    const form = new FormData();
    form.append("file", file);
    const out = await act<{ added_transactions: number }>("upload", "/api/ingest/statement", { method: "POST", body: form });
    if (out) setNotice({ tone: "info", text: `Added ${out.added_transactions} transactions from ${file.name}.` });
  }

  async function openPanel(id: string, kind: "cancel" | "cheaper") {
    setOpen(id);
    const data = kind === "cancel"
      ? await post<CancelPrep>(`row-${id}`, `/api/subscriptions/${id}/cancel-prep`)
      : await act<Alternatives>(`row-${id}`, `/api/subscriptions/${id}/alternatives`);
    if (data) setPanel({ id, p: kind === "cancel" ? { kind, data: data as CancelPrep } : { kind, data: data as Alternatives } });
  }

  async function negotiate(id: string) {
    setOpen(id);
    const data = await post<ActionPrep>(`row-${id}`, `/api/subscriptions/${id}/negotiate`);
    if (data) setPanel({ id, p: { kind: "negotiate", data } });
  }

  async function prepareFinding(id: string) {
    setFindOpen(id);
    const a = await post<ActionPrep>(`find-${id}`, `/api/findings/${id}/prepare`);
    if (a) setFindPrep({ id, a });
  }

  async function finishFinding(id: string, gotBack: number) {
    const out = await post<Finding>(`find-${id}`, `/api/findings/${id}/done`, { got_back: gotBack });
    if (out) { setFindOpen(null); setNotice({ tone: "info", text: `Nice. ${money(gotBack)} added to what you've recovered.` }); }
  }

  async function dismissFinding(id: string) {
    const out = await post<Finding>(`find-${id}`, `/api/findings/${id}/dismiss`);
    if (out) setFindOpen(null);
  }

  function pick(id: string) {
    setOpen(id);
    requestAnimationFrame(() => document.getElementById(`sub-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }));
  }

  const openFindings = findings.filter((f) => f.status === "open");
  const closedFindings = findings.length - openFindings.length;
  const owed = summary?.owed_total ?? openFindings.reduce((t, f) => t + f.amount, 0);
  const demo = (conns?.mode ?? "demo") === "demo";
  const save = summary?.potential_monthly_savings ?? 0;
  const MAIN: GroupKey[] = ["decide", "bills", "check"];
  const grouped = GROUPS.map((g) => ({
    ...g,
    rows: subs
      .filter((s) => groupOf(s) === g.key)
      .sort((a, b) => reclaimable(b) - reclaimable(a) || b.monthly_cost - a.monthly_cost),
  }));
  const rest = grouped.filter((g) => !MAIN.includes(g.key) && g.rows.length);

  return (
    <div className={intro ? "intro" : undefined}>
      <SiteNav current="dashboard">
        {!demo && <button disabled={busy === "sync"} onClick={() => post("sync", "/api/sync")}>{busy === "sync" ? "Syncing" : "Sync now"}</button>}
        <div className="connect-menu">
          <button className="solid" aria-expanded={connectOpen} aria-controls="connect-list" onClick={() => setConnectOpen((v) => !v)}>
            Connect <Chevron className={connectOpen ? "chev up" : "chev"} />
          </button>
          {connectOpen && (
            <div className="connect-list" id="connect-list">
              <ConnectButton name="email" c={conns?.email} detail={conns?.email.account} busy={busy === "email"}
                onConnect={connectEmail} onDisconnect={() => post("email", "/api/connect/email/disconnect")} />
              <ConnectButton name="bank" c={conns?.plaid} detail={conns?.plaid.institution} busy={busy === "plaid"}
                onConnect={connectBank} onDisconnect={() => post("plaid", "/api/connect/plaid/disconnect")} />
              <label className="btn file-btn">
                Upload a statement
                <input type="file" accept=".csv,.ofx,.qfx" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
              </label>
            </div>
          )}
        </div>
      </SiteNav>

      <section className="dash-head" aria-label="Your month">
        <div className="wrap">
          {summary && (
            <>
              <h1>
                You pay <span className="num">{money(summary.monthly_total)}</span> a month for {recurringLabel(summary)}.
                <span className="second">
                  <HeroSecond save={save} owed={owed} any={summary.subscriptions + (summary.bills ?? 0) > 0} />
                </span>
              </h1>
              <Donut groups={summary.spend_groups ?? []} selected={slice} onSelect={setSlice} />
              {(summary.trials ?? []).map((t) => (
                <p key={t.id} className="trial-note">
                  Plus a {money(t.amount)} {t.merchant} trial that starts charging {shortDate(t.starts_on)}.
                </p>
              ))}
              {slice && (() => {
                const g = (summary.spend_groups ?? []).find((x) => x.label === slice);
                if (!g) return null;
                return (
                  <section className="slice-list" aria-label={`${g.label}: what you pay`}>
                    <div className="slice-head">
                      <h2>{g.label} <span className="count">{money(g.monthly)} a month</span></h2>
                      <button className="quiet" onClick={() => setSlice(null)}>Show all</button>
                    </div>
                    <ul>
                      {g.items.map((it) => {
                        const s = subs.find((x) => x.id === it.id);
                        return (
                          <li key={it.id}>
                            <button className="svc-link" onClick={() => pick(it.id)}>{it.merchant}</button>
                            <span className="num">{money(it.monthly)}</span>
                            <span className="num">{it.could_cut > 0 ? <span className="hl">{money(it.could_cut)}</span> : <span className="nil">None</span>}</span>
                            <span className="act">
                              {s && <PrimaryAction s={s} busy={busy === `row-${s.id}`}
                                onCheckin={() => pick(s.id)}
                                onCancel={() => { pick(s.id); openPanel(s.id, "cancel"); }}
                                onCheaper={() => { pick(s.id); openPanel(s.id, "cheaper"); }}
                                onNegotiate={() => { pick(s.id); negotiate(s.id); }} />}
                            </span>
                          </li>
                        );
                      })}
                    </ul>
                  </section>
                );
              })()}
              <div className="legend">
                <RecoveredLegend s={summary} />
              </div>
            </>
          )}
        </div>
      </section>

      <main className="wrap dash-main" id="content">
        {notice && (
          <div className={`notice ${notice.tone}`} role="status">
            {notice.tone === "missing" && <span className="tag missing">Missing</span>}
            <p>{notice.tone === "missing" ? notice.text.replace(/^MISSING\s*(\[[^\]]+\])?:?\s*/i, "") : notice.text}</p>
            <button className="icon" aria-label="Dismiss" onClick={() => setNotice(null)}><Close /></button>
          </div>
        )}

        {guide && demo && (
          <p className="guide-line" role="note">
            <span>This is a made-up month. Click a slice, or open any row with a yellow amount.</span>
            <button className="quiet" onClick={closeGuide}>Got it</button>
          </p>
        )}

        {alerts && alerts.unseen > 0 && (
          <section className="alerts" aria-labelledby="h-alerts">
            <div className="alerts-head">
              <h2 id="h-alerts">New since you last looked <span className="count">{alerts.unseen}</span></h2>
              <button className="quiet" disabled={busy === "alerts"} onClick={seenAlerts}>Mark as seen</button>
            </div>
            <ul>
              {alerts.alerts.filter((a) => !a.seen).slice(0, 6).map((a) => (
                <li key={a.id}>
                  <b>{a.title}</b> <span>{humanDates(a.message)}</span>
                  {a.amount > 0 && <span className="hl num">{money(a.amount)}</span>}
                  <span className="when">{shortDate(a.created_at)}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {openFindings.length > 0 && (
          <section className="group owed" id="owed" aria-labelledby="h-owed">
            <div className="group-head">
              <h2 id="h-owed">Owed to you <span className="count">{openFindings.length}</span></h2>
              <span className="group-sum">{money(owed)} to claim</span>
            </div>
            <div className="sheet">
              <div className="row-line owed cols" aria-hidden>
                <span>From</span><span>What ClawBack found</span><span>Deadline</span><span className="num">Amount</span><span />
              </div>
              <ol className="rows">
                {openFindings.map((f) => (
                  <FindingRow
                    key={f.id}
                    f={f}
                    open={findOpen === f.id}
                    prep={findPrep?.id === f.id ? findPrep.a : null}
                    busy={busy === `find-${f.id}`}
                    onToggle={() => setFindOpen(findOpen === f.id ? null : f.id)}
                    onPrepare={() => prepareFinding(f.id)}
                    onClosePrep={() => setFindPrep(null)}
                    onDone={(v) => finishFinding(f.id, v)}
                    onDismiss={() => dismissFinding(f.id)}
                  />
                ))}
              </ol>
            </div>
            {closedFindings > 0 && <p className="fine-print after">{closedFindings} more marked done or dismissed.</p>}
          </section>
        )}

        {grouped.filter((g) => MAIN.includes(g.key)).map((g) => {
          if (!g.rows.length) return null;
          const cost = g.rows.reduce((t, s) => t + s.monthly_cost, 0);
          const sum = g.key === "cancelled" ? `${money(cost)} a month you no longer pay` : `${money(cost)} a month`;
          return (
            <section key={g.key} className={`group ${g.key}`} id={`g-${g.key}`} aria-labelledby={`h-${g.key}`}>
              <div className="group-head">
                <h2 id={`h-${g.key}`}>{g.title} <span className="count">{g.rows.length}</span></h2>
                <span className="group-sum">{sum}</span>
              </div>
              <div className="sheet">
                <div className="row-line cols" aria-hidden>
                  <span>{g.key === "bills" ? "Bill" : g.key === "fine" ? "Subscription or bill" : "Subscription"}</span><span>What ClawBack found</span><span className="num">Costs</span><span className="num">Could save</span><span />
                </div>
                <ol className="rows">
                  {g.rows.map((s) => (
                    <SubscriptionRow
                      key={s.id}
                      s={s}
                      open={open === s.id}
                      panel={panel?.id === s.id ? panel.p : null}
                      busy={busy === `row-${s.id}`}
                      onToggle={() => setOpen(open === s.id ? null : s.id)}
                      onCheckin={(used) => post(`row-${s.id}`, `/api/subscriptions/${s.id}/checkin`, { used })}
                      onKeep={() => { setPanel(null); post(`row-${s.id}`, `/api/subscriptions/${s.id}/keep`); }}
                      onCancel={() => openPanel(s.id, "cancel")}
                      onCheaper={() => openPanel(s.id, "cheaper")}
                      onNegotiate={() => negotiate(s.id)}
                      onClosePanel={() => setPanel(null)}
                    />
                  ))}
                </ol>
              </div>
            </section>
          );
        })}

        {(rest.length > 0 || (recovered?.events.length ?? 0) > 0) && (
          <details className="group rest">
            <summary>
              <span>Everything else: {restSummary(rest, recovered)}</span>
              <Chevron className="chev" />
            </summary>
        {rest.map((g) => {
          if (!g.rows.length) return null;
          const cost = g.rows.reduce((t, s) => t + s.monthly_cost, 0);
          const sum = g.key === "cancelled" ? `${money(cost)} a month you no longer pay` : `${money(cost)} a month`;
          return (
            <section key={g.key} className={`group ${g.key}`} id={`g-${g.key}`} aria-labelledby={`h-${g.key}`}>
              <div className="group-head">
                <h2 id={`h-${g.key}`}>{g.title} <span className="count">{g.rows.length}</span></h2>
                <span className="group-sum">{sum}</span>
              </div>
              <div className="sheet">
                <div className="row-line cols" aria-hidden>
                  <span>{g.key === "bills" ? "Bill" : g.key === "fine" ? "Subscription or bill" : "Subscription"}</span><span>What ClawBack found</span><span className="num">Costs</span><span className="num">Could save</span><span />
                </div>
                <ol className="rows">
                  {g.rows.map((s) => (
                    <SubscriptionRow
                      key={s.id}
                      s={s}
                      open={open === s.id}
                      panel={panel?.id === s.id ? panel.p : null}
                      busy={busy === `row-${s.id}`}
                      onToggle={() => setOpen(open === s.id ? null : s.id)}
                      onCheckin={(used) => post(`row-${s.id}`, `/api/subscriptions/${s.id}/checkin`, { used })}
                      onKeep={() => { setPanel(null); post(`row-${s.id}`, `/api/subscriptions/${s.id}/keep`); }}
                      onCancel={() => openPanel(s.id, "cancel")}
                      onCheaper={() => openPanel(s.id, "cheaper")}
                      onNegotiate={() => negotiate(s.id)}
                      onClosePanel={() => setPanel(null)}
                    />
                  ))}
                </ol>
              </div>
            </section>
          );
        })}

        {recovered && recovered.events.length > 0 && (
          <section className="group money-back" id="money-back" aria-labelledby="h-back">
            <div className="group-head">
              <h2 id="h-back">Money back <span className="count">{recovered.events.length}</span></h2>
              <span className="group-sum">{recovered.note}</span>
            </div>
            <div className="table-scroll sheet">
              <table>
                <thead><tr><th>When</th><th>From</th><th>What happened</th><th>Checked</th><th className="num">Amount</th></tr></thead>
                <tbody>
                  {recovered.events.map((e) => (
                    <tr key={e.id}>
                      <td>{shortDate(e.on)}</td>
                      <td>{e.merchant}</td>
                      <td>{e.kind === "cancelled_subscription" ? `Cancelled. ${humanDates(e.note)}` : humanDates(e.note)}</td>
                      <td>{e.status === "confirmed" ? <span className="tag ok"><Check /> In your bank data</span> : <span className="tag">You told us</span>}</td>
                      <td className="num">{e.monthly ? <>{money(e.monthly)} a month</> : money(e.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

          </details>
        )}


        <details className="trace" id="trace">
          <summary>
            <span>How ClawBack worked this out</span>
            <span className="trace-meta num">{trace.length} steps, {costLabel(trace)} in model costs</span>
            <Chevron className="chev" />
          </summary>
          <p className="fine-print">Each step records which engine ran it, how long it took and what it cost. Rows marked missing are stand-ins for parts not built yet; fallback rows are where a backup model took over.</p>
          <div className="table-scroll">
            <table className="trace-table">
              <thead><tr><th>Step</th><th>Tier</th><th>Engine</th><th>Result</th><th className="num">Time</th><th className="num">Tokens in, out</th><th className="num">Cost</th><th>Note</th></tr></thead>
              <tbody>
                {trace.map((t, i) => (
                  <tr key={i} className={t.status}>
                    <td>{t.stage}</td><td>{t.tier || "code"}</td><td><code>{t.engine}</code></td><td>{t.status}</td>
                    <td className="num">{t.ms.toFixed(1)} ms</td><td className="num">{t.input_tokens}, {t.output_tokens}{t.reasoning_tokens > 0 ? ` (+${t.reasoning_tokens} thinking)` : ""}</td>
                    <td className="num">${t.cost_usd.toFixed(5)}</td><td>{t.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </main>

      <footer className="site-foot">
        <div className="wrap">
          <p>ClawBack never cancels, pays, sends or files anything on its own. You make the final click.</p>
          <p className="foot-demo">
            <span>{demo ? "Prototype. Made-up demo month." : "Your data, kept on this computer."}</span>{" "}
            <a href="/built">What&apos;s built</a>
            {demo && <button className="quiet" disabled={!!busy} onClick={() => post("sync", "/api/sync")}>Re-run</button>}
            <button className="quiet" disabled={!!busy} onClick={() => { setPanel(null); setOpen(null); setSlice(null); post("seed", "/api/demo/seed"); }}>
              {demo ? "Reset demo data" : "Switch to demo data"}
            </button>
          </p>
        </div>
      </footer>
    </div>
  );
}

function recurringLabel(s: Summary) {
  const subs = `${s.subscriptions} subscription${s.subscriptions === 1 ? "" : "s"}`;
  const bills = s.bills ?? 0;
  return bills ? `${subs} and ${bills} bill${bills === 1 ? "" : "s"}` : subs;
}

function HeroSecond({ save, owed, any }: { save: number; owed: number; any: boolean }) {
  if (save > 0 && owed > 0) return <>You could save <span className="hl num">{money(save)}</span> a month and claim <span className="hl num">{money(owed)}</span> you&apos;re owed.</>;
  if (save > 0) return <>You could get back <span className="hl num">{money(save)}</span> of it.</>;
  if (owed > 0) return <>And you&apos;re owed <span className="hl num">{money(owed)}</span>.</>;
  return any ? <>Nothing looks wasted right now.</> : <>Connect your email or bank to find them.</>;
}

function ConnectButton({ name, c, detail, busy, onConnect, onDisconnect }: {
  name: string; c?: Connection; detail?: string | null; busy: boolean; onConnect: () => void; onDisconnect: () => void;
}) {
  if (c?.connected && c.needs_reconnect) {
    return (
      <button className="solid" disabled={busy} onClick={onConnect} title={c.error ?? undefined}>
        Reconnect {name} <span className="tag missing">Expired</span>
      </button>
    );
  }
  if (c?.connected) {
    return (
      <span className="linked" title={c.error ?? undefined}>
        <Check /> <span>{detail || (name === "bank" ? "Bank" : "Email")} connected</span>
        <button className="icon" aria-label={`Disconnect ${name}`} title={`Disconnect ${name}`} disabled={busy} onClick={onDisconnect}><Close /></button>
      </span>
    );
  }
  return (
    <button className="solid" disabled={busy} onClick={onConnect}>
      {busy ? "Connecting" : `Connect ${name}`}
      {c && !c.configured && <span className="tag missing">Keys needed</span>}
      {!c && <span className="tag missing">Not built</span>}
    </button>
  );
}

function costLabel(trace: TraceStep[]) {
  const total = trace.reduce((t, s) => t + s.cost_usd, 0);
  return `$${total.toFixed(total < 0.01 ? 4 : 2)}`;
}

function RecoveredLegend({ s }: { s: Summary }) {
  const confirmed = s.recovered_confirmed ?? 0;
  const told = s.recovered_self_reported ?? 0;
  const monthly = s.cancelled_monthly_savings ?? 0;
  return (
    <span className="recovered" title={s.recovered_note}>
      {monthly > 0 && <span>Cancelled <b>{money(monthly)}</b> a month</span>}
      <span>
        Got back <b>{money(s.recovered_total)}</b>
        {confirmed > 0 && told === 0 && <span className="tag ok">In your bank data</span>}
        {told > 0 && <span className="tag">{confirmed > 0 ? `${money(told)} you told us` : "You told us"}</span>}
      </span>
    </span>
  );
}

function restSummary(rest: { key: GroupKey; rows: Subscription[] }[], recovered: Recovered | null) {
  const parts: string[] = [];
  for (const g of rest) {
    if (g.key === "fine") parts.push(`${g.rows.length} look${g.rows.length === 1 ? "s" : ""} fine`);
    if (g.key === "cancelled") parts.push(`${g.rows.length} cancelled`);
  }
  const back = recovered?.events.reduce((t, e) => t + e.amount, 0) ?? 0;
  if (recovered && recovered.events.length) parts.push(back > 0 ? `${money(back)} saved so far` : `${recovered.events.length} money back`);
  return parts.join(", ");
}
