"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "./icons";

// Light or dark. The page follows the computer's setting until you pick one here, and picking the same as the
// computer goes back to following it. The choice stays in this browser only (localStorage); layout.tsx applies it
// before the first paint, so a dark page never flashes white. The icon itself is swapped by CSS (globals.css).
const KEY = "clawback.theme";
const systemDark = () => window.matchMedia("(prefers-color-scheme: dark)").matches;

export default function ThemeToggle() {
  const [dark, setDark] = useState<boolean | null>(null);

  useEffect(() => {
    const read = () => {
      const t = document.documentElement.dataset.theme;
      setDark(t ? t === "dark" : systemDark());
    };
    read();
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", read);
    return () => mq.removeEventListener("change", read);
  }, []);

  function flip() {
    const next = !(dark ?? systemDark());
    const apply = () => {
      const root = document.documentElement;
      if (next === systemDark()) {
        delete root.dataset.theme;
        try { localStorage.removeItem(KEY); } catch { /* follows the computer anyway */ }
      } else {
        root.dataset.theme = next ? "dark" : "light";
        try { localStorage.setItem(KEY, root.dataset.theme); } catch { /* this visit only */ }
      }
      setDark(next);
    };
    // A short crossfade where the browser supports it, unless the computer asks for less motion.
    const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown };
    if (doc.startViewTransition && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) doc.startViewTransition(apply);
    else apply();
  }

  return (
    <button className="icon theme-toggle" onClick={flip} aria-label="Dark mode" aria-pressed={dark ?? undefined}
      title={dark ? "Switch to light" : "Switch to dark"}>
      <Moon className="moon" />
      <Sun className="sun" />
    </button>
  );
}
