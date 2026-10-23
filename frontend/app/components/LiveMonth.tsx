"use client";

import { useEffect, useState } from "react";
import { call, type Summary } from "../api";
import { money } from "../format";

// The demo month in one sentence, read live from the backend. If the server is down, the numbers seeded on start-up stand in.
const SEEDED = { monthly_total: 503.23, potential_monthly_savings: 81.97, owed_total: 615.06, owed_count: 7 };

export default function LiveMonth() {
  const [s, setS] = useState<typeof SEEDED>(SEEDED);
  const [live, setLive] = useState(false);

  useEffect(() => {
    call<Summary>("/api/summary")
      .then((x) => {
        setS({ monthly_total: x.monthly_total, potential_monthly_savings: x.potential_monthly_savings, owed_total: x.owed_total ?? 0, owed_count: x.owed_count ?? 0 });
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
          <span className="hl num">{money(s.owed_total)}</span> owed back.
        </p>
        <small>{live ? "Live from the ClawBack server, on its demo data." : "The demo's starting numbers. The ClawBack server isn't answering, so these aren't live."}</small>
      </div>
    </section>
  );
}
