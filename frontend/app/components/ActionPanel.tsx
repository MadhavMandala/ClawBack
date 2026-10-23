"use client";

import type { ActionPrep } from "../api";
import { humanDates, shortDate } from "../format";
import { CopyButton, Missing } from "./bits";
import SaveDraft from "./SaveDraft";
import { Check, External } from "./icons";

const CHANNEL: Record<ActionPrep["channel"], string> = {
  email: "Send this email",
  chat: "Paste this into their chat",
  phone: "Say this on the call",
  form: "Fill in their form",
  dispute: "File this dispute",
  in_person: "Take this to the store",
};

// A prepared request: what to do, where, and the words to use. ClawBack never sends it.
// draftPath: the route that saves the message as a draft in the person's mailbox, when it can be emailed.
export default function ActionPanel({ a, onClose, draftPath }: { a: ActionPrep; onClose: () => void; draftPath?: string }) {
  const by = shortDate(a.deadline);
  const letter = a.message ? [a.message.subject && `Subject: ${a.message.subject}`, a.message.body].filter(Boolean).join("\n\n") : "";
  return (
    <section className="panel" aria-label={a.title}>
      <div className="panel-head">
        <h3>{a.title}</h3>
        <button className="quiet" onClick={onClose}>Close</button>
      </div>
      <p>
        {humanDates(a.summary)}
        {by && <> Do it by <b>{by}</b>.</>} ClawBack never sends anything for you.
      </p>

      <div className="panel-grid">
        <div>
          <h4>Steps</h4>
          <ol className="steps">{a.steps.map((st, i) => <li key={i}>{humanDates(st)}</li>)}</ol>
          {a.links.length > 0 && (
            <ul className="links">
              {a.links.map((l) => (
                <li key={l.url}>
                  <a href={l.url} target="_blank" rel="noreferrer">{l.label}<External className="ext" /></a>
                  {l.verified ? <span className="tag ok"><Check /> Checked link</span> : <span className="tag missing">Unchecked</span>}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          {a.message && (
            <>
              <h4>{CHANNEL[a.channel] ?? "The message"}</h4>
              <div className="letter">
                {a.message.to && <p className="letter-to">To: {a.message.to}</p>}
                {a.message.subject && <p className="letter-subject">{a.message.subject}</p>}
                <p className="letter-body">{a.message.body}</p>
              </div>
              <div className="pair">
                <CopyButton text={letter} label="Copy message" />
                {draftPath && <SaveDraft path={draftPath} subject={a.message.subject} body={a.message.body} to={a.message.to} />}
              </div>
            </>
          )}
          {a.script && a.script.length > 0 && (
            <>
              <h4 className={a.message ? "gap-top" : undefined}>{a.message ? "If you call instead" : CHANNEL[a.channel]}</h4>
              <ul className="script">{a.script.map((line, i) => <li key={i}>{line}</li>)}</ul>
            </>
          )}
        </div>
      </div>

      {a.missing.map((m, i) => <Missing key={i}>{m}</Missing>)}
    </section>
  );
}
