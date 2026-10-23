"use client";

import { useState } from "react";
import type { ActionPrep, Alternatives, CancelPrep, Subscription } from "../api";
import { humanDates, isBill, leadFlag, money, planLine, reclaimable, shortDate, sources } from "../format";
import ActionPanel from "./ActionPanel";
import { Missing } from "./bits";
import { Check, Chevron, External } from "./icons";
import SaveDraft from "./SaveDraft";

export type RowPanel =
  | { kind: "cancel"; data: CancelPrep }
  | { kind: "cheaper"; data: Alternatives }
  | { kind: "negotiate"; data: ActionPrep }
  | null;

type Props = {
  s: Subscription;
  open: boolean;
  panel: RowPanel;
  busy: boolean;
  onToggle: () => void;
  onCheckin: (used: boolean) => void;
  onKeep: () => void;
  onCancel: () => void;
  onCheaper: () => void;
  onNegotiate: () => void;
  onClosePanel: () => void;
};

export default function SubscriptionRow(p: Props) {
  const { s, open } = p;
  const lead = leadFlag(s);
  const save = reclaimable(s);
  const detailId = `detail-${s.id}`;
  const others = s.flags.filter((f) => f !== lead);

  return (
    <li className={`row${open ? " open" : ""}`} id={`sub-${s.id}`}>
      <div className="row-line">
        <div className="c-svc">
          <button className="svc-toggle" aria-expanded={open} aria-controls={detailId} onClick={p.onToggle}>
            <span className="svc-name">{s.merchant}</span>
            <Chevron className="chev" />
          </button>
          {s.status === "trial" && <span className="tag">Free trial</span>}
          <span className="svc-plan">{planLine(s)}</span>
        </div>

        <p className={`c-find ${lead?.severity ?? "none"}`}>{lead ? humanDates(lead.message) : "Nothing to flag. You seem to use it."}</p>

        <span className="c-cost num">{money(s.monthly_cost)}</span>

        <span className="c-save num">{save > 0 ? <span className="hl">{money(save)}</span> : <span className="nil">None</span>}</span>

        <div className="c-act">
          <PrimaryAction s={s} busy={p.busy} onCheckin={p.onCheckin} onCancel={p.onCancel} onCheaper={p.onCheaper} onNegotiate={p.onNegotiate} />
        </div>
      </div>

      {open && (
        <div className="detail" id={detailId}>
          <div className="detail-grid">
            <div>
              <h3>What ClawBack saw</h3>
              <ul className="evidence">
                {others.map((f, i) => <li key={`f${i}`} className={f.severity}>{humanDates(f.message)}</li>)}
                {s.usage.evidence.map((e, i) => <li key={i}>{humanDates(e)}</li>)}
                {!others.length && !s.usage.evidence.length && <li>No usage signals yet.</li>}
              </ul>
              <p className="fine-print">
                Found in {sources(s)}. Charged {s.charge_count} time{s.charge_count === 1 ? "" : "s"}
                {s.last_charged ? `, last on ${shortDate(s.last_charged)}` : ""}.
              </p>
            </div>
            <div className="detail-actions">
              {isBill(s) ? (
                <>
                  <h3>Pay less for {s.merchant}</h3>
                  <div className="pair">
                    <button disabled={p.busy} className="solid" onClick={p.onNegotiate}>Get a negotiation script</button>
                    <button disabled={p.busy} onClick={p.onCheaper}>Find a cheaper plan</button>
                    <button disabled={p.busy} onClick={p.onKeep}>Keep it</button>
                  </div>
                </>
              ) : (
                <>
                  <h3>Did you use {s.merchant} this month?</h3>
                  <div className="pair">
                    <button disabled={p.busy} onClick={() => p.onCheckin(true)}>Yes, I used it</button>
                    <button disabled={p.busy} onClick={() => p.onCheckin(false)}>No</button>
                  </div>
                  <div className="pair">
                    <button disabled={p.busy} onClick={p.onKeep}>Keep it</button>
                    <button disabled={p.busy} onClick={p.onCheaper}>Find a cheaper option</button>
                    <button disabled={p.busy} className="solid" onClick={p.onCancel}>Help me cancel</button>
                  </div>
                </>
              )}
            </div>
          </div>

          {p.panel?.kind === "cancel" && <CancelPanel d={p.panel.data} onClose={p.onClosePanel} />}
          {p.panel?.kind === "cheaper" && <CheaperPanel d={p.panel.data} onClose={p.onClosePanel} />}
          {p.panel?.kind === "negotiate" && <ActionPanel a={p.panel.data} onClose={p.onClosePanel} />}
        </div>
      )}
    </li>
  );
}

function PrimaryAction({ s, busy, onCheckin, onCancel, onCheaper, onNegotiate }: {
  s: Subscription; busy: boolean; onCheckin: (u: boolean) => void; onCancel: () => void; onCheaper: () => void; onNegotiate: () => void;
}) {
  const lead = leadFlag(s);
  if (!lead) return null;
  if (lead.kind === "bill_increase" || lead.kind === "promo_ending" || lead.kind === "negotiable") {
    return <button className={lead.kind === "negotiable" ? undefined : "solid"} disabled={busy} onClick={onNegotiate}>Negotiate it down</button>;
  }
  if (lead.kind === "trial_ending") {
    const by = shortDate(s.next_expected);
    return <button className="solid" disabled={busy} onClick={onCancel}>{by ? `Cancel before ${by}` : "Help me cancel"}</button>;
  }
  if (lead.kind === "unused" || lead.kind === "membership_losing_money") {
    return <button className="solid" disabled={busy} onClick={onCancel}>Help me cancel</button>;
  }
  if (lead.kind === "overlap" || lead.kind === "price_increase") {
    return <button disabled={busy} onClick={onCheaper}>Find a cheaper option</button>;
  }
  if (lead.kind === "unknown_usage" || s.usage.needs_checkin) {
    return (
      <div className="ask" role="group" aria-label={`Did you use ${s.merchant} this month?`}>
        <span>Used it?</span>
        <button disabled={busy} onClick={() => onCheckin(true)}>Yes</button>
        <button disabled={busy} onClick={() => onCheckin(false)}>No</button>
      </div>
    );
  }
  return null;
}

function CancelPanel({ d, onClose }: { d: CancelPrep; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const by = shortDate(d.next_charge);
  async function copy() {
    try {
      await navigator.clipboard.writeText(`Subject: ${d.email.subject}\n\n${d.email.body}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* clipboard blocked: the text is still on screen to select */ }
  }
  return (
    <section className="panel" aria-label={`Cancel ${d.merchant}`}>
      <div className="panel-head">
        <h3>Cancel {d.merchant}</h3>
        <button className="quiet" onClick={onClose}>Close</button>
      </div>
      <p>
        Cancelling saves <span className="hl">{money(d.you_save_per_month)}</span> a month{by ? `. Do it before ${by}, when the next charge lands.` : "."}{" "}
        ClawBack never cancels or sends anything for you. You make the final click.
      </p>
      <div className="panel-grid">
        <div>
          <h4>Steps</h4>
          <ol className="steps">{d.steps.map((st, i) => <li key={i}>{st}</li>)}</ol>
          {d.links.length > 0 && (
            <ul className="links">
              {d.links.map((l) => (
                <li key={l.url}>
                  <a href={l.url} target="_blank" rel="noreferrer">{l.label}<External className="ext" /></a>
                  {l.verified ? <span className="tag ok"><Check /> Checked link</span> : <span className="tag missing">Unchecked</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h4>Or send this email</h4>
          <div className="letter">
            {d.email.to && <p className="letter-to">To: {d.email.to}</p>}
            <p className="letter-subject">{d.email.subject}</p>
            <p className="letter-body">{d.email.body}</p>
          </div>
          <div className="pair">
            <button onClick={copy}>{copied ? "Copied" : "Copy email"}</button>
            <SaveDraft path={`/api/subscriptions/${d.subscription_id}/email-draft`} subject={d.email.subject} body={d.email.body} to={d.email.to} />
          </div>
          <p className="fine-print after">{d.email.status}</p>
        </div>
      </div>
      {d.missing.map((m, i) => <Missing key={i}>{m}</Missing>)}
    </section>
  );
}

function CheaperPanel({ d, onClose }: { d: Alternatives; onClose: () => void }) {
  return (
    <section className="panel" aria-label="Cheaper options">
      <div className="panel-head">
        <h3>Cheaper ways to get what you use</h3>
        <button className="quiet" onClick={onClose}>Close</button>
      </div>
      {d.options.length > 0 && (
        <ul className="options">
          {d.options.map((o, i) => (
            <li key={i}>
              <b>{o.option}</b>{o.monthly_price != null && <span className="num"> {money(o.monthly_price)} a month</span>}
              <span>{o.why}</span>
              <a href={o.source_url} target="_blank" rel="noreferrer">Source<External className="ext" /></a>
            </li>
          ))}
        </ul>
      )}
      <ul className="hints">{d.hints.map((h, i) => <li key={i}>{h}</li>)}</ul>
      {d.missing.map((m, i) => <Missing key={i}>{m}</Missing>)}
    </section>
  );
}
