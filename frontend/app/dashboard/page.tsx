"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  API, call,
  type ActionPrep, type Alerts, type Alternatives, type CancelPrep, type Connection, type Connections,
  type Finding, type Recovered, type Showcase as ShowcaseData, type Subscription, type Summary, type TraceStep,
} from "../api";
import Showcase from "../components/Showcase";
import { bankNotice, connectBank as openPlaid, connectEmail as openEmailSignIn } from "../connect";
import { groupOf, humanDates, money, reclaimable, shortDate, type GroupKey } from "../format";
import { FindingDetail, FindingLine } from "../components/FindingRow";
import SiteNav from "../components/SiteNav";
import Donut from "../components/Donut";
import { SubscriptionDetail, SubscriptionLine, type RowPanel } from "../components/SubscriptionRow";
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
const MAIN: GroupKey[] = ["decide", "bills", "check"]; // open on the page; the rest fold into "Everything else"

export default function Dashboard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [subs, setSubs] = useState<Subscription[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [findPrep, setFindPrep] = useState<{ id: string; a: ActionPrep } | null>(null);
  const [trace, setTrace] = useState<TraceStep[]>([]);
  const [conns, setConns] = useState<Connections | null>(null);
  // The row shown in the detail pane. One at a time, across findings and subscriptions.
  const [sel, setSel] = useState<{ kind: "sub" | "finding"; id: string } | null>(null);
  const paneRef = useRef<HTMLElement>(null);
  const [panel, setPanel] = useState<{ id: string; p: RowPanel } | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [intro, setIntro] = useState(true);
  const [ready, setReady] = useState(false);
  const [alerts, setAlerts] = useState<Alerts | null>(null);
  const [recovered, setRecovered] = useState<Recovered | null>(null);
  const [showcase, setShowcase] = useState<ShowcaseData | null>(null);
  const [guide, setGuide] = useState(false);
  const [filter, setFilter] = useState<string | null>(null); // a donut group: the list shows only its services
  const [connectOpen, setConnectOpen] = useState(false);
  const [restOpen, setRestOpen] = useState(false);
  const connectRef = useRef<HTMLDivElement>(null);
  const connectBtn = useRef<HTMLButtonElement>(null);

  // The Connect menu closes on a click outside it or on Escape (focus goes back to its button).
  useEffect(() => {
    if (!connectOpen) return;
    const away = (e: PointerEvent) => { if (!connectRef.current?.contains(e.target as Node)) setConnectOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") { setConnectOpen(false); connectBtn.current?.focus(); } };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", esc); };
  }, [connectOpen]);
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
      setShowcase(await call<ShowcaseData>("/api/showcase").catch(() => null));
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
    if (q.get("connected") === "email-send") setNotice({ tone: "info", text: "Email connected for sending only. Your demo month stays, and nothing is read from your inbox." });
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

  async function uploadTimeline(file: File) {
    const form = new FormData();
    form.append("file", file);
    const out = await act<{ visits: number; gyms: string[] }>("upload", "/api/ingest/timeline", { method: "POST", body: form });
    if (out) setNotice({ tone: "info", text: out.visits
      ? `Read your Google Maps Timeline: ${out.visits} gym visits (${out.gyms.join(", ")}). Only those visit dates were kept.`
      : "Read your Google Maps Timeline. No visits to a gym ClawBack knows, so nothing was kept." });
  }

  async function openPanel(id: string, kind: "cancel" | "cheaper") {
    setSel({ kind: "sub", id });
    const data = kind === "cancel"
      ? await post<CancelPrep>(`row-${id}`, `/api/subscriptions/${id}/cancel-prep`)
      : await act<Alternatives>(`row-${id}`, `/api/subscriptions/${id}/alternatives`);
    if (data) setPanel({ id, p: kind === "cancel" ? { kind, data: data as CancelPrep } : { kind, data: data as Alternatives } });
  }

  async function markCancelled(id: string) {
    const out = await post<Subscription>(`row-${id}`, `/api/subscriptions/${id}/cancelled`);
    if (out) setNotice({ tone: "info", text: `Marked ${out.merchant} as cancelled. ClawBack will check your bank for the next charge.` });
  }

  async function negotiate(id: string) {
    setSel({ kind: "sub", id });
    const data = await post<ActionPrep>(`row-${id}`, `/api/subscriptions/${id}/negotiate`);
    if (data) setPanel({ id, p: { kind: "negotiate", data } });
  }

  async function prepareFinding(id: string) {
    setSel({ kind: "finding", id });
    const a = await post<ActionPrep>(`find-${id}`, `/api/findings/${id}/prepare`);
    if (a) setFindPrep({ id, a });
  }

  async function finishFinding(id: string, gotBack: number) {
    const out = await post<Finding>(`find-${id}`, `/api/findings/${id}/done`, { got_back: gotBack });
    if (out) { setSel(null); setFindPrep(null); setNotice({ tone: "info", text: `Nice. ${money(gotBack)} added to what you've recovered.` }); }
  }

  async function dismissFinding(id: string) {
    const out = await post<Finding>(`find-${id}`, `/api/findings/${id}/dismiss`);
    if (out) { setSel(null); setFindPrep(null); }
  }

  // Show a row in the pane. Rows that look fine, cancelled ones and money back live in the "Everything else" fold,
  // so it opens first; the list line scrolls into view.
  function select(kind: "sub" | "finding", id: string) {
    setSel({ kind, id });
    if (kind === "sub") {
      const target = subs.find((x) => x.id === id);
      if (target && !MAIN.includes(groupOf(target))) setRestOpen(true);
    }
    setTimeout(() => document.getElementById(`${kind === "sub" ? "sub" : "find"}-${id}`)?.scrollIntoView({ block: "nearest" }), 60);
  }

  const openFindings = findings.filter((f) => f.status === "open");
  const closedFindings = findings.length - openFindings.length;
  // Only the money the page shows: the price-drop card. Other findings are hidden from the dashboard for now.
  const owed = openFindings.find((f) => f.id === showcase?.price?.finding_id)?.amount ?? 0;
  const demo = (conns?.mode ?? "demo") === "demo";
  const save = summary?.potential_monthly_savings ?? 0;
  const grouped = GROUPS.map((g) => ({
    ...g,
    rows: subs
      .filter((s) => groupOf(s) === g.key)
      .sort((a, b) => reclaimable(b) - reclaimable(a) || b.monthly_cost - a.monthly_cost),
  }));
  const rest = grouped.filter((g) => !MAIN.includes(g.key) && g.rows.length);
  // The three workflows lead the page; everything else folds away, minus what already has a card.
  const onCards = new Set([showcase?.gym?.sub_id, showcase?.streaming?.sub_id].filter(Boolean) as string[]);
  const others = grouped
    .map((g) => ({ ...g, rows: g.rows.filter((s) => !onCards.has(s.id)) }))
    .filter((g) => g.rows.length);
  const otherCount = others.reduce((t, g) => t + g.rows.length, 0);
  const inFilter = filter ? new Set((summary?.spend_groups ?? []).find((g) => g.label === filter)?.items.map((i) => i.id) ?? []) : null;
  const shown = (rows: Subscription[]) => (inFilter ? rows.filter((s) => inFilter.has(s.id)) : rows);
  const selSub = sel?.kind === "sub" ? subs.find((x) => x.id === sel.id) ?? null : null;
  const selFinding = sel?.kind === "finding" ? findings.find((x) => x.id === sel.id) ?? null : null;
  const output = (selSub && panel?.id === selSub.id) || (selFinding && findPrep?.id === selFinding.id);

  // On a wide screen the pane is never empty: show the first thing owed (or to decide on). On a phone the pane
  // is a sheet over the list, so nothing opens until you tap a row.
  useEffect(() => {
    if (sel || !ready || typeof window === "undefined" || !window.matchMedia("(min-width: 761px)").matches) return;
    // The first workflow card: the gym, else the streaming service, else the price drop.
    const card = showcase?.gym?.sub_id ?? showcase?.streaming?.sub_id;
    if (card) setSel({ kind: "sub", id: card });
    else if (showcase?.price?.finding_id) setSel({ kind: "finding", id: showcase.price.finding_id });
  }, [sel, ready, showcase]);

  // When ClawBack writes something, the pane jumps to its top, where the output is.
  useEffect(() => {
    if (output) paneRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  }, [output, panel, findPrep]);

  return (
    <div className={intro ? "intro" : undefined}>
      <SiteNav current="dashboard">
        {!demo && <button disabled={busy === "sync"} onClick={() => post("sync", "/api/sync")}>{busy === "sync" ? "Syncing" : "Sync now"}</button>}
        <div className="connect-menu" ref={connectRef}>
          <button ref={connectBtn} className="solid" aria-expanded={connectOpen} aria-controls="connect-list" onClick={() => setConnectOpen((v) => !v)}>
            Connect
            {(conns?.email.needs_reconnect || conns?.plaid.needs_reconnect) && <span className="tag missing">Reconnect</span>}
            <Chevron className={connectOpen ? "chev up" : "chev"} />
          </button>
          <div className="connect-list" id="connect-list" hidden={!connectOpen}>
            <ConnectButton name="email" c={conns?.email} detail={conns?.email.account} busy={busy === "email"}
              onConnect={() => { setConnectOpen(false); connectEmail(); }} onDisconnect={() => { setConnectOpen(false); post("email", "/api/connect/email/disconnect"); }} />
            <ConnectButton name="bank" c={conns?.plaid} detail={conns?.plaid.institution} busy={busy === "plaid"}
              onConnect={() => { setConnectOpen(false); connectBank(); }} onDisconnect={() => { setConnectOpen(false); post("plaid", "/api/connect/plaid/disconnect"); }} />
            <label className="btn file-btn">
              Upload a statement
              <input type="file" accept=".csv,.ofx,.qfx" hidden onChange={(e) => { const f = e.target.files?.[0]; setConnectOpen(false); if (f) upload(f); e.target.value = ""; }} />
            </label>
            <label className="btn file-btn" title="From the Google Maps app: Settings, then Location or Personal content, then Export Timeline data">
              Upload Google Maps Timeline
              <input type="file" accept=".json,application/json" hidden onChange={(e) => { const f = e.target.files?.[0]; setConnectOpen(false); if (f) uploadTimeline(f); e.target.value = ""; }} />
            </label>
          </div>
        </div>
      </SiteNav>

      <main className="wrap dash-grid" id="content">
        <aside className="dash-left" aria-label="Your month">
          {summary && (
            <>
              <h1>
                You pay <span className="num">{money(summary.monthly_total)}</span> a month for {recurringLabel(summary)}.
                <span className="second">
                  <HeroSecond save={save} owed={owed} any={summary.subscriptions + (summary.bills ?? 0) > 0} />
                </span>
              </h1>
              <Donut groups={summary.spend_groups ?? []} selected={filter} onSelect={setFilter} />
              {(summary.trials ?? []).map((t) => (
                <p key={t.id} className="trial-note">
                  Plus a {money(t.amount)} {t.merchant} trial that starts charging {shortDate(t.starts_on)}.
                </p>
              ))}
              <div className="legend">
                <RecoveredLegend s={summary} />
              </div>
            </>
          )}
        </aside>

        <section className="dash-list" aria-label="What ClawBack found">
        {notice && (
          <div className={`notice ${notice.tone}`} role="status">
            {notice.tone === "missing" && <span className="tag missing">Missing</span>}
            <p>{notice.tone === "missing" ? notice.text.replace(/^MISSING\s*(\[[^\]]+\])?:?\s*/i, "") : notice.text}</p>
            <button className="icon" aria-label="Dismiss" onClick={() => setNotice(null)}><Close /></button>
          </div>
        )}

        {guide && demo && (
          <p className="guide-line" role="note">
            <span>This is a made-up month. Click a slice to filter the list, or pick any row to see what ClawBack can do.</span>
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

          {filter && (
            <p className="filter-line">
              <span>Showing <b>{filter}</b></span>
              <button className="quiet" onClick={() => setFilter(null)}>Show all</button>
            </p>
          )}

          {!filter && (
            <Showcase data={showcase} subs={subs} findings={openFindings}
              onOpen={(kind, id, action) => {
                select(kind, id);
                if (kind === "sub" && action === "cancel") openPanel(id, "cancel");
              }} />
          )}

          {(others.length > 0 || (recovered?.events.length ?? 0) > 0) && (
            <details className="group rest" open={restOpen || !!filter} onToggle={(e) => setRestOpen(e.currentTarget.open)}>
              <summary>
                <span>
                  Everything else: {otherCount} more subscription{otherCount === 1 ? "" : "s"} and bills
                  {recovered && recovered.events.length > 0 ? `, ${restSummary([], recovered)}` : ""}
                </span>
                <Chevron className="chev" />
              </summary>
              {others.map((g) => {
                const rows = shown(g.rows);
                if (!rows.length) return null;
                return (
                  <section key={g.key} className={`group ${g.key}`} id={`g-${g.key}`} aria-labelledby={`h-${g.key}`}>
                    <div className="group-head">
                      <h2 id={`h-${g.key}`}>{g.title} <span className="count">{rows.length}</span></h2>
                    </div>
                    <ul className="lines">
                      {rows.map((s) => (
                        <SubscriptionLine key={s.id} s={s} selected={sel?.kind === "sub" && sel.id === s.id} onSelect={() => select("sub", s.id)} />
                      ))}
                    </ul>
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
        </section>

        <aside className={`dash-pane${sel ? " has-sel" : ""}`} id="pane" ref={paneRef} aria-label="Details">
          {sel && <button className="pane-back quiet" onClick={() => { setSel(null); setPanel(null); setFindPrep(null); }}>Back to the list</button>}
          {selFinding ? (
            <FindingDetail
              key={selFinding.id}
              f={selFinding}
              prep={findPrep?.id === selFinding.id ? findPrep.a : null}
              busy={busy === `find-${selFinding.id}`}
              onPrepare={() => prepareFinding(selFinding.id)}
              onClosePrep={() => setFindPrep(null)}
              onDone={(v) => finishFinding(selFinding.id, v)}
              onDismiss={() => dismissFinding(selFinding.id)}
            />
          ) : selSub ? (
            <SubscriptionDetail
              key={selSub.id}
              s={selSub}
              panel={panel?.id === selSub.id ? panel.p : null}
              busy={busy === `row-${selSub.id}`}
              onCheckin={(used) => post(`row-${selSub.id}`, `/api/subscriptions/${selSub.id}/checkin`, { used })}
              onKeep={() => { setPanel(null); post(`row-${selSub.id}`, `/api/subscriptions/${selSub.id}/keep`); }}
              onCancel={() => openPanel(selSub.id, "cancel")}
              onCheaper={() => openPanel(selSub.id, "cheaper")}
              onNegotiate={() => negotiate(selSub.id)}
              onClosePanel={() => setPanel(null)}
              onCancelled={() => markCancelled(selSub.id)}
              onSent={() => load()}
            />
          ) : (
            <p className="pane-empty">Pick anything on the list to see what ClawBack found and what it can write for you.</p>
          )}
        </aside>
      </main>

      <div className="wrap">
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
      </div>

      <footer className="site-foot">
        <div className="wrap">
          <p>ClawBack never cancels, pays or files anything. It sends one email, a gym cancellation, only when you click Send.</p>
          <p className="foot-demo">
            <span>{demo ? "Prototype. Made-up demo month." : "Your own data, from your connections."}</span>{" "}
            <a href="/built">What&apos;s built</a>
            {demo && <button className="quiet" disabled={!!busy} onClick={() => post("sync", "/api/sync")}>Re-run</button>}
            <button className="quiet" disabled={!!busy} onClick={() => { setPanel(null); setFindPrep(null); setSel(null); setFilter(null); post("seed", "/api/demo/seed"); }}>
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
