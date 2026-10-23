import Link from "next/link";
import { Logo } from "./icons";

// The bar along the top of both pages. Each page passes its own controls for the right-hand end.
export default function SiteNav({ current, children }: { current?: "home" | "dashboard"; children?: React.ReactNode }) {
  return (
    <header className="site-nav">
      <a className="skip" href="#content">Skip to content</a>
      <div className="wrap">
        <Link className="brand" href="/"><Logo /> <span>ClawBack</span></Link>
        <nav className="nav-links" aria-label="Pages">
          <Link href="/" aria-current={current === "home" ? "page" : undefined}>Overview</Link>
          <Link href="/dashboard" aria-current={current === "dashboard" ? "page" : undefined}>Dashboard</Link>
          <Link href="/dashboard#build-status">What&apos;s built</Link>
        </nav>
        {children && <div className="nav-end">{children}</div>}
      </div>
    </header>
  );
}
