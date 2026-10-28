import Link from "next/link";
import { Logo } from "./icons";
import ThemeToggle from "./ThemeToggle";

// The bar along the top of every page. Each page passes its own controls for the right-hand end, after the
// light/dark toggle.
export default function SiteNav({ current, children }: { current?: "home" | "dashboard" | "settings" | "built"; children?: React.ReactNode }) {
  return (
    <header className="site-nav">
      <a className="skip" href="#content">Skip to content</a>
      <div className="wrap">
        <Link className="brand" href="/"><Logo /> <span>ClawBack</span></Link>
        <nav className="nav-links" aria-label="Pages">
          <Link href="/" aria-current={current === "home" ? "page" : undefined}>Overview</Link>
          <Link href="/dashboard" aria-current={current === "dashboard" ? "page" : undefined}>Dashboard</Link>
          <Link href="/settings" aria-current={current === "settings" ? "page" : undefined}>Your data</Link>
        </nav>
        <div className="nav-end"><ThemeToggle />{children}</div>
      </div>
    </header>
  );
}
