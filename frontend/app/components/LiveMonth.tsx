"use client";

import { useEffect, useState } from "react";
import { call, type Finding, type Showcase, type Summary } from "../api";
import { money } from "../format";

// The demo month in one sentence, read live from the backend. If the server is down, the demo's usual numbers stand in.
// "Owed" is the price drop the dashboard shows, so the two pages agree.
const SEEDED = { monthly_total: 672.23, potential_monthly_savings: 258.97, owed: 84.01 };

export default function LiveMonth() {
  const [s, setS] = useState<typeof SEEDED>(SEEDED);
  const [live, setLive] = useState(false);

  useEffect(() => {
    Promise.all([call<Summary>("/api/summary"), call<Showcase>("/api/showcase"), call<Finding[]>("/api/findings")])
      .then(([x, show, findings]) => {
        const owed = findings.find((f) => f.id === show.price?.finding_id)?.amount ?? 0;
        setS({ monthly_total: x.monthly_total, potential_monthly_savings: x.potential_monthly_savings, owed });
        setLive(true);
      })
      .catch(() => setLive(false));
  }, []);

  return (
    <section className="lp-month" aria-label="What ClawBack found in the demo month">
      <div className="wrap">
        <p>
          In one demo month of <span className="num">{money(s.monthly_total)}</span> in recurring charges, ClawBack found{" "}
          <span className="hl num">{money(s.potential_monthly_savings)}</span> a month to stop paying and{" "}
          <span className="hl num">{money(s.owed)}</span> owed back on one purchase.
        </p>
        <small>{live ? "Live from the ClawBack server, on its demo data." : "The demo's starting numbers. The ClawBack server isn't answering, so these aren't live."}</small>
      </div>
    </section>
  );
}
