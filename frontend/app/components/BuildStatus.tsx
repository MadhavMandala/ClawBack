"use client";

import { useState } from "react";
import type { Features, PhaseId } from "../api";
import { shortDate } from "../format";

const PHASE_COLOR: Record<PhaseId, string> = {
  planned: "var(--phase-planned)",
  started: "var(--phase-started)",
  built: "var(--phase-built)",
  live: "var(--phase-live)",
};

// Every feature the project planned, and how far along it is. The list comes from backend/clawback/features.py.
export default function BuildStatus({ data }: { data: Features | null }) {
  const [only, setOnly] = useState<PhaseId | "all">("all");

  if (!data) {
    return (
      <section className="build" id="build-status" aria-labelledby="h-build">
        <div className="build-head"><h2 id="h-build">What&apos;s built</h2></div>
        <p className="build-lead">The feature list comes from the ClawBack server, which isn&apos;t answering right now.</p>
      </section>
    );
  }

  const total = data.features.length;
  const c = data.counts;
  const shown = data.features.filter((f) => only === "all" || f.phase === only);
  const ladder = [...data.phases].reverse(); // most finished first, left to right

  return (
    <section className="build" id="build-status" aria-labelledby="h-build">
      <div className="build-head">
        <h2 id="h-build">What&apos;s built</h2>
        <span className="fine-print">Updated {shortDate(data.updated) ?? data.updated}</span>
      </div>
      <p className="build-lead">
        <b className="num">{total}</b> features planned for this prototype. <b className="num">{c.live}</b> have run against
        the real services, <b className="num">{c.built}</b> more work on demo data, <b className="num">{c.started}</b> are
        started and <b className="num">{c.planned}</b> aren&apos;t started yet.
      </p>

      <div className="ladder">
        <div className="ladder-bar" role="img" aria-label={ladder.map((p) => `${p.label}: ${c[p.id]}`).join(", ")}>
          {ladder.map((p) => c[p.id] > 0 && <span key={p.id} style={{ flexGrow: c[p.id], background: PHASE_COLOR[p.id] }} />)}
        </div>
        <ol className="ladder-steps">
          {ladder.map((p) => (
            <li key={p.id} style={{ ["--c" as string]: PHASE_COLOR[p.id] }}>
              <b><span className="num">{c[p.id]}</span> {p.label}</b>
              <p>{p.description}</p>
            </li>
          ))}
        </ol>
      </div>

      <div className="phase-filter" role="group" aria-label="Show features by phase">
        <button aria-pressed={only === "all"} onClick={() => setOnly("all")}>All <span className="num">{total}</span></button>
        {ladder.map((p) => (
          <button key={p.id} aria-pressed={only === p.id} onClick={() => setOnly(only === p.id ? "all" : p.id)}>
            {p.label} <span className="num">{c[p.id]}</span>
          </button>
        ))}
      </div>

      <div className="build-areas">
        {data.areas.map((area) => {
          const feats = shown.filter((f) => f.area === area);
          if (!feats.length) return null;
          return (
            <div className="build-area" key={area}>
              <h3>{area} <span className="count num">{feats.length}</span></h3>
              <ol className="feats">
                {feats.map((f) => {
                  const phase = data.phases.find((p) => p.id === f.phase);
                  return (
                    <li className="feat" key={f.id} id={`feature-${f.id}`}>
                      <div>
                        <p className="feat-name">
                          {f.name}
                          {f.priority && <span className={`tag prio ${f.priority.toLowerCase()}`} title={PRIORITY[f.priority]}>{f.priority}</span>}
                        </p>
                        <p className="feat-sum">{f.summary}</p>
                        {f.next && <p className="feat-next"><span>Next: </span>{f.next}</p>}
                        {f.where !== "not started" && <code className="feat-where">{f.where}</code>}
                      </div>
                      <div className="feat-phase" data-phase={f.phase}>
                        <span className="pips" data-phase={f.phase} aria-hidden><i /><i /><i /><i /></span>
                        <span>{phase?.label ?? f.phase}</span>
                      </div>
                    </li>
                  );
                })}
              </ol>
            </div>
          );
        })}
      </div>
    </section>
  );
}

const PRIORITY: Record<string, string> = {
  P0: "Needed for the hackathon demo",
  P1: "Needed for a convincing submission",
  P2: "Roadmap",
};
