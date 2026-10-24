"use client";

import { useState } from "react";
import { calendarFile, downloadCalendar } from "../ics";
import { writtenBy, type ActionPrep, type Alternatives, type CancelPrep, type Subscription } from "../api";
import { daysLeft, humanDates, isBill, leadFlag, money, planLine, reclaimable, shortDate, sources } from "../format";
import ActionPanel from "./ActionPanel";
import { Missing } from "./bits";
import { Chevron, External } from "./icons";
import SaveDraft from "./SaveDraft";

export type RowPanel =
  | { kind: "cancel"; data: CancelPrep }
  | { kind: "cheaper"; data: Alternatives }
  | { kind: "negotiate"; data: ActionPrep }
  | null;

// A short label for the list: what ClawBack found, in a few words (the pane has the full sentence).
const SHORT: Record<string, string> = {
  unused: "Looks unused",
  membership_losing_money: "Costs more than it saves",
  paid_twice: "Paying twice",
  included_elsewhere: "Included elsewhere",
  overlap: "Two plans, one job",
  price_increase: "Price went up",
  bill_increase: "Went up",
  promo_ending: "Promo rate ending",
  negotiable: "Could be lower",
  unknown_usage: "Used it this month?",
  cancel_pending: "Cancelling",
  cancel_confirmed: "Cancelled",
  charged_after_cancel: "Charged after you cancelled",
};

export function shortFinding(s: Subscription): string {
  const lead = leadFlag(s);
  if (s.status === "cancelled") return "Cancelled";
  if (lead?.kind === "trial_ending") return s.next_expected ? `Trial ends ${shortDate(s.next_expected)}` : "Trial ending";
  if (lead && SHORT[lead.kind]) return SHORT[lead.kind];
  return "Looks fine";
}

// One line in the middle list. Selecting it fills the detail pane.
export function SubscriptionLine({ s, selected, onSelect }: { s: Subscription; selected: boolean; onSelect: () => void }) {
  const save = reclaimable(s);
  return (
    <li className={`line${selected ? " on" : ""}`} id={`sub-${s.id}`}>
      <button className="line-btn" aria-current={selected ? "true" : undefined} aria-controls="pane" onClick={onSelect}>
        <span className="line-name">{s.merchant}</span>
        <span className="line-what">{shortFinding(s)}</span>
        <span className="line-amt num">{save > 0 ? <span className="hl">{money(save)}</span> : <span className="nil">{money(s.monthly_cost)}</span>}</span>
      </button>
    </li>
  );
}

type DetailProps = {
  s: Subscription;
  panel: RowPanel;
  busy: boolean;
  onCheckin: (used: boolean) => void;
  onKeep: () => void;
  onCancel: () => void;
  onCheaper: () => void;
  onNegotiate: () => void;
  onClosePanel: () => void;
  onCancelled: () => void;
};

// The detail pane for a subscription or bill. Anything ClawBack writes (the cancel panel, cheaper options, a
// negotiation script) sits at the top, so it's in view the moment it arrives.
export function SubscriptionDetail(p: DetailProps) {
  const { s } = p;
  const lead = leadFlag(s);
  const save = reclaimable(s);
  const others = s.flags.filter((f) => f !== lead);

  return (
    <article className="pane-body" aria-label={s.merchant}>
      {p.panel?.kind === "cancel" && <CancelPanel d={p.panel.data} trial={s.status === "trial"} busy={p.busy} onClose={p.onClosePanel} onCancelled={p.onCancelled} />}
      {p.panel?.kind === "cheaper" && <CheaperPanel d={p.panel.data} onClose={p.onClosePanel} />}
      {p.panel?.kind === "negotiate" && <ActionPanel a={p.panel.data} onClose={p.onClosePanel} />}

      <header className="pane-head">
        <h2>
          {s.merchant}
          {s.status === "trial" && <span className="tag">Free trial</span>}
        </h2>
        <p className="pane-sub">{money(s.monthly_cost)} a month{planLine(s) ? `. ${planLine(s)}` : ""}.</p>
        {save > 0 && <p className="pane-save">Could save <span className="hl">{money(save)}</span> a month</p>}
      </header>

      <p className={`pane-find ${lead?.severity ?? "none"}`}>{lead ? humanDates(lead.message) : "Nothing to flag. You seem to use it."}</p>

      {!p.panel && (
        <div className="pane-acts">
          {s.status === "cancelled" ? (
            <p className="fine-print">ClawBack keeps watching your bank and tells you if {s.merchant} charges you again.</p>
          ) : isBill(s) ? (
            <div className="pair">
              <button disabled={p.busy} className="solid" onClick={p.onNegotiate}>Get a negotiation script</button>
              <button disabled={p.busy} onClick={p.onCheaper}>Find a cheaper plan</button>
              <button disabled={p.busy} className="quiet" onClick={p.onKeep}>Keep it</button>
            </div>
          ) : (
            <>
              {(lead?.kind === "unknown_usage" || s.usage.needs_checkin) && (
                <div className="ask" role="group" aria-label={`Did you use ${s.merchant} this month?`}>
                  <span>Did you use it this month?</span>
                  <button disabled={p.busy} onClick={() => p.onCheckin(true)}>Yes</button>
                  <button disabled={p.busy} onClick={() => p.onCheckin(false)}>No</button>
                </div>
              )}
              <div className="pair">
                {lead?.kind !== "cancel_pending" && lead?.kind !== "cancel_confirmed" && (
                  <button disabled={p.busy} className="solid" onClick={p.onCancel}>
                    {lead?.kind === "trial_ending" && s.next_expected ? `Cancel before ${shortDate(s.next_expected)}` : "Help me cancel"}
                  </button>
                )}
                <button disabled={p.busy} onClick={p.onCheaper}>Find a cheaper option</button>
                <button disabled={p.busy} className="quiet" onClick={p.onKeep}>Keep it</button>
              </div>
            </>
          )}
        </div>
      )}

      <section className="pane-evidence">
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
      </section>
    </article>
  );
}

// The row's one button. Check-ins ("Did you use it?") open the row; the Yes / No buttons live inside it.
export function PrimaryAction({ s, busy, onOpen, onCancel, onCheaper, onNegotiate }: {
  s: Subscription; busy: boolean; onOpen: () => void; onCancel: () => void; onCheaper: () => void; onNegotiate: () => void;
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
  if (lead.kind === "cancel_pending" || lead.kind === "cancel_confirmed") return null;
  if (lead.kind === "charged_after_cancel") {
    return <button className="solid" disabled={busy} onClick={onCancel}>Cancel again</button>;
  }
  if (lead.kind === "unused" || lead.kind === "membership_losing_money" || lead.kind === "paid_twice" || lead.kind === "included_elsewhere") {
    return <button className="solid" disabled={busy} onClick={onCancel}>Help me cancel</button>;
  }
  if (lead.kind === "overlap" || lead.kind === "price_increase") {
    return <button disabled={busy} onClick={onCheaper}>Find a cheaper option</button>;
  }
  if (lead.kind === "unknown_usage" || s.usage.needs_checkin) {
    return <button disabled={busy} onClick={onOpen}>Did you use it?</button>;
  }
  return null;
}

function CancelPanel({ d, trial, busy, onClose, onCancelled }: {
  d: CancelPrep; trial: boolean; busy: boolean; onClose: () => void; onCancelled: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const next = shortDate(d.next_charge);
  const remindDay = shortDate(d.reminder_on);
  const remindToday = d.reminder_on ? daysLeft(d.reminder_on) === 0 : false;
  const link = d.primary_link;

  async function copy() {
    if (!d.email) return;
    try {
      await navigator.clipboard.writeText(`Subject: ${d.email.subject}\n\n${d.email.body}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* clipboard blocked: the text is still on screen to select */ }
  }

  function remind() {
    if (!d.reminder_on) return;
    const steps = d.how_to.map((st, i) => `${i + 1}. ${st}`).join("\n");
    const text = calendarFile({
      id: d.subscription_id,
      title: next ? `Cancel ${d.merchant} before ${next}` : `Cancel ${d.merchant}`,
      date: d.reminder_on,
      description: [link ? `${link.label}: ${link.url}` : "", steps].filter(Boolean).join("\n\n"),
      url: link?.url ?? null,
    });
    downloadCalendar(`cancel-${d.subscription_id}.ics`, text);
  }

  return (
    <section className="panel cancel" aria-label={`Cancel ${d.merchant}`}>
      <div className="panel-head">
        <h3>Cancel {d.merchant}</h3>
        <button className="quiet" onClick={onClose}>Close</button>
      </div>
      <p className="cancel-line">
        {trial
          ? <>Ends {next}, then <span className="hl">{money(d.you_save_per_month)}</span>/month.</>
          : <>Saves <span className="hl">{money(d.you_save_per_month)}</span> a month.{next ? ` Next charge ${next}.` : ""}</>}
      </p>

      <div className="cancel-actions">
        {link && (
          <a className="btn solid big" href={link.url} target="_blank" rel="noreferrer">
            {link.label}<External className="ext" />
          </a>
        )}
        {d.reminder_on && <button onClick={remind}>{remindToday ? "Remind me today" : `Remind me on ${remindDay}`}</button>}
      </div>
      {link && <p className="fine-print">Opens {link.host}.</p>}

      {(d.how_to.length > 0 || (d.rights?.length ?? 0) > 0) && (
        <details className="how-to">
          <summary>How to cancel on {d.merchant}<Chevron className="chev" /></summary>
          <ol className="steps">
            {d.how_to.map((st, i) => <li key={i}>{st}</li>)}
            {(d.rights ?? []).map((r) => (
              <li key={r.source_url}>
                {r.text} <a href={r.source_url} target="_blank" rel="noreferrer">{r.title}<External className="ext" /></a>
              </li>
            ))}
          </ol>
        </details>
      )}

      {d.email && (
        <div className="cancel-email">
          <p>Or email them{d.email.to ? <> at <b>{d.email.to}</b></> : null}. Their help page says they accept it.</p>
          <details>
            <summary>Show the email{writtenBy(d.email.written_by) && <span className="tag">{writtenBy(d.email.written_by)}</span>}</summary>
            <div className="letter">
              {d.email.to && <p className="letter-to">To: {d.email.to}</p>}
              <p className="letter-subject">{d.email.subject}</p>
              <p className="letter-body">{d.email.body}</p>
            </div>
            <div className="pair">
              <button onClick={copy}>{copied ? "Copied" : "Copy email"}</button>
              <SaveDraft path={`/api/subscriptions/${d.subscription_id}/email-draft`} subject={d.email.subject} body={d.email.body} to={d.email.to} />
            </div>
          </details>
        </div>
      )}

      <div className="cancel-done">
        <span>Done it?</span>
        <button className="solid" disabled={busy} onClick={() => { onCancelled(); onClose(); }}>I cancelled it</button>
        <button className="quiet" onClick={onClose}>Not yet</button>
      </div>
      {d.watch_after && (
        <p className="fine-print">ClawBack then checks your bank after {shortDate(d.watch_after)} and tells you if {d.merchant} charged anyway.</p>
      )}
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
