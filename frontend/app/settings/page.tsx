"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { call, forgetSession, type Me, type Settings as StateSettings } from "../api";
import { bankNotice, connectBank, connectEmail } from "../connect";
import { shortDate } from "../format";
import InstallApp from "../components/InstallApp";
import SiteNav from "../components/SiteNav";
import { Check, External } from "../components/icons";
import "./settings.css";

type Notice = { tone: "info" | "error"; text: string } | null;

function Sec({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section className="st-sec" id={id} aria-labelledby={`h-${id}`}>
      <h2 id={`h-${id}`}>{title}</h2>
      <div className="st-body">{children}</div>
    </section>
  );
}

const PROVIDER: Record<string, string> = {
  google: "Gmail", microsoft: "Outlook", yahoo: "Yahoo Mail", icloud: "iCloud Mail", imap: "IMAP", ews: "Exchange",
};

export default function Settings() {
  const [me, setMe] = useState<Me | null>(null);
  const [st, setSt] = useState<StateSettings | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [deleted, setDeleted] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [m, s] = await Promise.all([call<Me>("/api/me"), call<StateSettings>("/api/settings")]);
      setMe(m); setSt(s);
    } catch (e) {
      setNotice({ tone: "error", text: `Can't reach the ClawBack server. ${(e as Error).message}` });
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function run(key: string, job: () => Promise<string | void>) {
    setBusy(key);
    try {
      const text = await job();
      if (text) setNotice({ tone: "info", text });
      await load();
    } catch (e) {
      setNotice({ tone: "error", text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  const disconnect = (source: "email" | "plaid") =>
    run(source, async () => {
      await call(`/api/connect/${source}/disconnect`, { method: "POST" });
      return source === "email" ? "Email disconnected. ClawBack dropped the mail it had read." : "Bank disconnected. ClawBack dropped its transactions.";
    });

  async function deleteAll() {
    setBusy("delete");
    try {
      const out = await call<{ ok: boolean; removed: Record<string, unknown> }>("/api/me", { method: "DELETE" });
      forgetSession();
      const gone = [
        out.removed.email_connection ? "your email connection" : null,
        out.removed.bank_connection ? "your bank connection" : null,
      ].filter(Boolean).join(" and ");
      setDeleted(gone ? `Deleted ${gone}, and everything ClawBack found.` : "Deleted everything ClawBack held for this browser.");
      setMe(null);
      setConfirming(false);
    } catch (e) {
      setNotice({ tone: "error", text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  const pickState = (code: string) =>
    run("state", async () => {
      const out = await call<StateSettings>("/api/settings/state", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ state: code || null }),
      });
      setSt(out);
      return out.state_rule ? `Saved. Cancel steps now include ${out.state_name}'s rule.` : out.state ? `Saved. ClawBack has no ${out.state_name} rule yet, so cancel steps show the federal one.` : "Cleared.";
    });

  const email = me?.connections.email;
  const bank = me?.connections.plaid;
  const spent = me?.model_spend_today_usd ?? 0;
  const limit = me?.model_daily_limit_usd ?? 0;

  return (
    <div className="st">
      <SiteNav current="settings">
        <Link className="btn solid" href="/dashboard">Back to the dashboard</Link>
      </SiteNav>

      <main id="content" className="wrap">
        <div className="st-hero">
          <h1>Your data. <em>What this browser&apos;s ClawBack holds, and how to remove it.</em></h1>
        </div>

        {notice && (
          <div className={`notice ${notice.tone}`} role="status">
            <p>{notice.text}</p>
            <button className="icon" aria-label="Dismiss" onClick={() => setNotice(null)}>×</button>
          </div>
        )}

        {deleted ? (
          <Sec id="deleted" title="Deleted">
            <p className="st-done"><Check /> {deleted}</p>
            <p>This browser no longer has a ClawBack session. Opening the dashboard starts a fresh demo month.</p>
            <p><Link className="btn" href="/dashboard">Start a fresh demo</Link></p>
          </Sec>
        ) : (
          <>
            <Sec id="session" title="This browser">
              <p>
                This browser has its own ClawBack session{me?.session.created_at ? <>, started <b>{shortDate(me.session.created_at)}</b></> : null}.
                It isn&apos;t tied to your name, and there&apos;s no password.
                {me?.session.deleted_after_idle_days ? <> After {me.session.deleted_after_idle_days} days without a visit, it&apos;s deleted along with any connections.</> : null}
              </p>
              <p>{me ? (me.mode === "demo" ? "It's showing the demo month: made-up charges and emails." : "It's showing your own data from the connections below.") : "Loading."}</p>
            </Sec>

            <Sec id="connections" title="Connections">
              <ul className="st-conns">
                <li>
                  <div>
                    <b>Email</b>
                    <span>
                      {email?.connected
                        ? <>{email.account ?? "Connected"}{email.provider ? `, ${PROVIDER[email.provider] ?? email.provider}` : ""}. Read-only, plus drafts if you allowed them.</>
                        : "Not connected. ClawBack reads receipts and billing emails, never your other mail."}
                    </span>
                    {email?.needs_reconnect && <span className="tag missing">Expired. Connect again.</span>}
                  </div>
                  {email?.connected && !email.needs_reconnect
                    ? <button disabled={!!busy} onClick={() => disconnect("email")}>{busy === "email" ? "Disconnecting" : "Disconnect"}</button>
                    : <button className="solid" disabled={!!busy} onClick={() => run("email", async () => { await connectEmail(); })}>{email?.needs_reconnect ? "Reconnect email" : "Connect email"}</button>}
                </li>
                <li>
                  <div>
                    <b>Bank</b>
                    <span>
                      {bank?.connected
                        ? <>{bank.institution ?? "Connected"}, through Plaid. ClawBack sees transactions, never your bank password.</>
                        : "Not connected. The demo uses Plaid's test bank, so no real account is needed."}
                    </span>
                    {bank?.needs_reconnect && <span className="tag missing">Expired. Connect again.</span>}
                  </div>
                  {bank?.connected && !bank.needs_reconnect
                    ? <button disabled={!!busy} onClick={() => disconnect("plaid")}>{busy === "plaid" ? "Disconnecting" : "Disconnect"}</button>
                    : <button className="solid" disabled={!!busy} onClick={() => run("plaid", async () => { const r = await connectBank(); return r ? bankNotice(r) : undefined; })}>{bank?.needs_reconnect ? "Reconnect bank" : "Connect bank"}</button>}
                </li>
              </ul>
              <p className="fine-print">Disconnecting removes the connection at Nylas or Plaid and drops what came from it.</p>
            </Sec>

            <Sec id="state" title="Your state">
              <p>
                Some states give you extra rights when you cancel, such as cancelling online the same way you signed up.
                Tell ClawBack your state and its cancel steps will say which rule applies.
              </p>
              <label className="st-select">
                <span>State</span>
                <select value={st?.state ?? ""} disabled={!st || busy === "state"} onChange={(e) => pickState(e.target.value)}>
                  <option value="">Not set</option>
                  {st?.states.map((x) => <option key={x.code} value={x.code}>{x.name}{x.has_rule ? "" : " (federal rule only)"}</option>)}
                </select>
              </label>
              {st?.state_rule && (
                <div className="st-rule">
                  <b>{st.state_rule.title}</b>
                  <p>{st.state_rule.user_right}</p>
                  <a href={st.state_rule.source_url} target="_blank" rel="noreferrer">Read the law<External className="ext" /></a>
                  <span className="fine-print"> Checked {shortDate(st.state_rule.checked_on)}. Not legal advice.</span>
                </div>
              )}
            </Sec>

            <Sec id="stored" title="What's stored">
              {me && (
                <div className="table-scroll">
                  <table>
                    <tbody>
                      <tr><td>Subscriptions</td><td className="num">{me.counts.subscriptions}</td></tr>
                      <tr><td>Bills</td><td className="num">{me.counts.bills}</td></tr>
                      <tr><td>Money owed to you</td><td className="num">{me.counts.findings}</td></tr>
                      <tr><td>Bank transactions</td><td className="num">{me.counts.transactions}</td></tr>
                      <tr><td>Emails read</td><td className="num">{me.counts.emails}</td></tr>
                      <tr><td>Alerts</td><td className="num">{me.counts.alerts}</td></tr>
                    </tbody>
                  </table>
                </div>
              )}
              <p>
                Everything is kept encrypted in one database on the ClawBack server. The text of your emails is never written
                to disk: ClawBack keeps the facts it read from each one, like a price or a renewal date.
              </p>
            </Sec>

            <Sec id="phone" title="On your phone">
              <p>
                ClawBack installs on your home screen and opens full screen, like an app. The installed app starts its
                own session, so connect your email or bank there too.
              </p>
              <InstallApp />
            </Sec>

            <Sec id="models" title="AI use today">
              <p>
                <b>${spent.toFixed(spent < 0.01 ? 4 : 2)}</b> of this session&apos;s{" "}
                <span>${limit.toFixed(2)}</span> daily limit, on NVIDIA Nemotron models through Nebius Token Factory.
              </p>
              {limit > 0 && (
                <div className="st-meter" role="img" aria-label={`${Math.round(Math.min(1, spent / limit) * 100)} percent of today's limit used`}>
                  <span style={{ width: `${Math.min(100, (spent / limit) * 100)}%` }} />
                </div>
              )}
              <p>When the limit is reached, ClawBack uses plain rules and templates until tomorrow. Nothing breaks; the letters are just less tailored.</p>
            </Sec>

            <Sec id="delete" title="Delete everything">
              <p>
                This removes your email and bank connections at Nylas and Plaid, and every subscription, finding, alert and fact
                ClawBack holds for this browser. It can&apos;t be undone.
              </p>
              {confirming ? (
                <div className="st-confirm" role="group" aria-label="Confirm delete">
                  <span>Delete all of it now?</span>
                  <button className="danger" disabled={busy === "delete"} onClick={deleteAll}>{busy === "delete" ? "Deleting" : "Yes, delete it"}</button>
                  <button disabled={busy === "delete"} onClick={() => setConfirming(false)}>Keep it</button>
                </div>
              ) : (
                <p><button className="danger" disabled={!me || !!busy} onClick={() => setConfirming(true)}>Delete all my data</button></p>
              )}
              <p className="fine-print">More on what ClawBack does with data in the <Link href="/privacy">privacy policy</Link>.</p>
            </Sec>
          </>
        )}
      </main>

      <footer className="site-foot">
        <div className="wrap">
          <p>ClawBack never cancels, pays or files anything. It sends one email, a gym cancellation, only when you click Send.</p>
          <p><Link href="/privacy">Privacy policy</Link></p>
        </div>
      </footer>
    </div>
  );
}
