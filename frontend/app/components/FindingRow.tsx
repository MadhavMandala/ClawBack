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

type Props = {
  f: Finding;
  open: boolean;
  prep: ActionPrep | null;
  busy: boolean;
  onToggle: () => void;
  onPrepare: () => void;
  onClosePrep: () => void;
  onDone: (gotBack: number) => void;
  onDismiss: () => void;
};

export default function FindingRow(p: Props) {
  const { f, open } = p;
  const [gotBack, setGotBack] = useState(String(f.amount || ""));
  const left = daysLeft(f.deadline);
  const detailId = `fdetail-${f.id}`;

  return (
    <li className={`row${open ? " open" : ""}`} id={`find-${f.id}`}>
      <div className="row-line owed">
        <div className="c-svc">
          <button className="svc-toggle" aria-expanded={open} aria-controls={detailId} onClick={p.onToggle}>
            <span className="svc-name">{f.merchant}</span>
            <Chevron className="chev" />
          </button>
          <span className="svc-plan">{KIND_LABEL[f.kind]}{f.confidence === "low" ? ", might apply" : ""}</span>
        </div>

        <p className="c-find">{humanDates(f.kind === "settlement" ? f.title : f.message)}</p>

        <span className={`c-due${left !== null && left <= 7 ? " soon" : ""}`}>
          {f.deadline ? <>{shortDate(f.deadline)}<span className="due-left">{left !== null ? dueText(left) : ""}</span></> : <span className="nil">No deadline</span>}
        </span>

        <span className="c-save num">{f.amount > 0 ? <span className="hl">{money(f.amount)}</span> : <span className="nil">Unknown</span>}</span>

        <div className="c-act">
          <button className={f.confidence === "low" ? undefined : "solid"} disabled={p.busy} onClick={p.onPrepare}>{ACTION_LABEL[f.kind]}</button>
        </div>
      </div>

      {open && (
        <div className="detail" id={detailId}>
          <div className="detail-grid">
            <div>
              {f.kind === "settlement" && <p className="who">{humanDates(f.message)}</p>}
              <h3>What ClawBack saw</h3>
              <ul className="evidence">{f.evidence.map((e, i) => <li key={i}>{humanDates(e)}</li>)}</ul>
              {f.amount_note && <p className="fine-print">{f.amount_note}</p>}
              {f.rule && (
                <div className="rule">
                  <h3>{f.rule.name}</h3>
                  <p>{f.rule.summary}</p>
                  <a href={f.rule.source_url} target="_blank" rel="noreferrer">Read the rule<External className="ext" /></a>
                </div>
              )}
            </div>
            <div className="detail-actions">
              <h3>Got it back?</h3>
              <form className="pair" onSubmit={(e) => { e.preventDefault(); const v = parseFloat(gotBack); if (v >= 0) p.onDone(v); }}>
                <label className="amount">
                  <span>$</span>
                  <input inputMode="decimal" aria-label="Amount you got back" value={gotBack} onChange={(e) => setGotBack(e.target.value)} />
                </label>
                <button type="submit" disabled={p.busy}>Mark as done</button>
              </form>
              <div className="pair">
                <button disabled={p.busy} onClick={p.onPrepare}>{ACTION_LABEL[f.kind]}</button>
                <button disabled={p.busy} className="quiet" onClick={p.onDismiss}>Not for me</button>
              </div>
              {f.kind === "settlement" && (
                <p className="fine-print">You file settlement claims yourself, on the official site. Claims are made under penalty of perjury, so only claim if you qualify.</p>
              )}
            </div>
          </div>
          {p.prep && <ActionPanel a={p.prep} onClose={p.onClosePrep} draftPath={`/api/findings/${f.id}/email-draft`} />}
        </div>
      )}
    </li>
  );
}

function dueText(left: number) {
  if (left < 0) return "Passed";
  if (left === 0) return "Today";
  if (left === 1) return "Tomorrow";
  return `In ${left} days`;
}
