"use client";

import { useState } from "react";
import type { ActionPrep, Finding } from "../api";
import { daysLeft, humanDates, money, shortDate } from "../format";
import ActionPanel from "./ActionPanel";
import { Chevron, External } from "./icons";

export const KIND_LABEL: Record<Finding["kind"], string> = {
  price_drop: "Price drop",
  flight_refund: "Flight refund",
  flight_compensation: "Flight compensation",
  duplicate_charge: "Duplicate charge",
  bank_fee: "Bank fee",
  settlement: "Settlement",
};

const ACTION_LABEL: Record<Finding["kind"], string> = {
  price_drop: "Claim the difference",
  flight_refund: "Request the refund",
  flight_compensation: "Claim compensation",
  duplicate_charge: "Dispute it",
  bank_fee: "Ask for it back",
  settlement: "Check if you qualify",
};

// One line in the middle list. Selecting it fills the detail pane.
export function FindingLine({ f, selected, onSelect }: { f: Finding; selected: boolean; onSelect: () => void }) {
  const left = daysLeft(f.deadline);
  return (
    <li className={`line${selected ? " on" : ""}`} id={`find-${f.id}`}>
      <button className="line-btn" aria-current={selected ? "true" : undefined} aria-controls="pane" onClick={onSelect}>
        <span className="line-name">{f.merchant}</span>
        <span className="line-what">
          {KIND_LABEL[f.kind]}
          {f.deadline && left !== null && left >= 0 && <span className={left <= 7 ? "soon" : undefined}>, {dueText(left).toLowerCase()}</span>}
        </span>
        <span className="line-amt num">{f.amount > 0 ? <span className="hl">{money(f.amount)}</span> : <span className="nil">Unknown</span>}</span>
      </button>
    </li>
  );
}

type DetailProps = {
  f: Finding;
  prep: ActionPrep | null;
  busy: boolean;
  onPrepare: () => void;
  onClosePrep: () => void;
  onDone: (gotBack: number) => void;
  onDismiss: () => void;
};

// The detail pane for money you're owed. The letter or script ClawBack writes goes at the top, so it's in view the
// moment it arrives; the long policy text is folded.
export function FindingDetail(p: DetailProps) {
  const { f } = p;
  const [gotBack, setGotBack] = useState(String(f.amount || ""));
  const left = daysLeft(f.deadline);

  return (
    <article className="pane-body" aria-label={`${f.merchant}: ${KIND_LABEL[f.kind]}`}>
      {p.prep && <ActionPanel a={p.prep} onClose={p.onClosePrep} draftPath={`/api/findings/${f.id}/email-draft`} />}

      <header className="pane-head">
        <h2>{f.merchant}<span className="tag">{KIND_LABEL[f.kind]}{f.confidence === "low" ? ", might apply" : ""}</span></h2>
        {f.amount > 0
          ? <p className="pane-save">Ask for <span className="hl">{money(f.amount)}</span> back</p>
          : <p className="pane-sub">Amount unknown</p>}
        {f.deadline && (
          <p className={`pane-sub${left !== null && left <= 7 ? " soon" : ""}`}>
            By {shortDate(f.deadline)}{left !== null ? ` (${dueText(left).toLowerCase()})` : ""}
          </p>
        )}
      </header>

      <p className="pane-find">{humanDates(f.kind === "settlement" ? f.title : f.message)}</p>
      {f.kind === "settlement" && <p className="fine-print">{humanDates(f.message)}</p>}

      {!p.prep && (
        <div className="pane-acts">
          <div className="pair">
            <button className={f.confidence === "low" ? undefined : "solid"} disabled={p.busy} onClick={p.onPrepare}>{ACTION_LABEL[f.kind]}</button>
            <button disabled={p.busy} className="quiet" onClick={p.onDismiss}>Not for me</button>
          </div>
        </div>
      )}

      <section className="pane-evidence">
        <h3>What ClawBack saw</h3>
        <ul className="evidence">{f.evidence.slice(0, 3).map((e, i) => <li key={i}>{humanDates(e)}</li>)}</ul>
        {(f.evidence.length > 3 || f.rule || f.amount_note) && (
          <details className="more">
            <summary>{f.rule ? `Show ${f.merchant}'s full policy` : "Show more"}<Chevron className="chev" /></summary>
            {f.evidence.length > 3 && <ul className="evidence">{f.evidence.slice(3).map((e, i) => <li key={i}>{humanDates(e)}</li>)}</ul>}
            {f.amount_note && <p className="fine-print">{f.amount_note}</p>}
            {f.rule && (
              <div className="rule">
                <h3>{f.rule.name}</h3>
                <p>{f.rule.summary}</p>
                <a href={f.rule.source_url} target="_blank" rel="noreferrer">Read the rule<External className="ext" /></a>
              </div>
            )}
          </details>
        )}
      </section>

      <section className="pane-done">
        <h3>Got it back?</h3>
        <form className="pair" onSubmit={(e) => { e.preventDefault(); const v = parseFloat(gotBack); if (v >= 0) p.onDone(v); }}>
          <label className="amount">
            <span>$</span>
            <input inputMode="decimal" aria-label="Amount you got back" value={gotBack} onChange={(e) => setGotBack(e.target.value)} />
          </label>
          <button type="submit" disabled={p.busy}>Mark as done</button>
        </form>
        {f.kind === "settlement" && (
          <p className="fine-print">You file settlement claims yourself, on the official site. Claims are made under penalty of perjury, so only claim if you qualify.</p>
        )}
      </section>
    </article>
  );
}

function dueText(left: number) {
  if (left < 0) return "Passed";
  if (left === 0) return "Today";
  if (left === 1) return "Tomorrow";
  return `In ${left} days`;
}
