"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { call, type Features, type PhaseId } from "../api";

const COLOR: Record<PhaseId, string> = {
  live: "var(--phase-live)", built: "var(--phase-built)", started: "var(--phase-started)", planned: "var(--phase-planned)",
};
const ORDER: PhaseId[] = ["live", "built", "started", "planned"];

// The front page's pointer to the full feature list on the dashboard.
export default function BuildTeaser() {
  const [f, setF] = useState<Features | null>(null);
  useEffect(() => { call<Features>("/api/features").then(setF).catch(() => setF(null)); }, []);

  return (
    <div className="lp-build">
      <div>
        <h2>A prototype, labelled honestly.</h2>
        <p>
          Every feature we planned is on the dashboard with how far along it is: planned, started, built on demo
          data, or tested against the real services.
        </p>
      </div>
      <div>
        {f ? (
          <>
            <div className="ladder-bar" role="img" aria-label={ORDER.map((p) => `${p}: ${f.counts[p]}`).join(", ")}>
              {ORDER.map((p) => f.counts[p] > 0 && <span key={p} style={{ flexGrow: f.counts[p], background: COLOR[p] }} />)}
            </div>
            <div className="key">
              {ORDER.map((p) => (
                <span key={p}><i style={{ background: COLOR[p] }} /><b className="num">{f.counts[p]}</b> {f.phases.find((x) => x.id === p)?.label}</span>
              ))}
            </div>
          </>
        ) : (
          <p>The list loads from the ClawBack server, which isn&apos;t answering right now.</p>
        )}
        <Link className="btn" href="/dashboard#build-status">See every feature</Link>
      </div>
    </div>
  );
}
