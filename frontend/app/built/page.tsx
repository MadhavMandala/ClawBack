"use client";

import { useEffect, useState } from "react";
import { call, type Features } from "../api";
import BuildStatus from "../components/BuildStatus";
import SiteNav from "../components/SiteNav";
import "../dashboard/dashboard.css";

// Every feature the project planned and how far along it is. Moved off the dashboard so the dashboard stays
// about your money; judges and the team find it here and from the footer.
export default function Built() {
  const [features, setFeatures] = useState<Features | null>(null);
  useEffect(() => {
    call<Features>("/api/features").then(setFeatures).catch(() => setFeatures(null));
  }, []);
  return (
    <>
      <SiteNav current="built" />
      <main className="wrap dash-main" id="content">
        <BuildStatus data={features} />
      </main>
      <footer className="site-foot">
        <div className="wrap">
          <p>Prototype. The full list of what&apos;s missing is in STATUS.md.</p>
          <p><a href="/dashboard">Back to the dashboard</a></p>
        </div>
      </footer>
    </>
  );
}
