"use client";

import { useState } from "react";

// Backend notes start with "MISSING [id]:". The tag already says that, so drop the prefix.
export const stripMissing = (s: string) => s.replace(/^MISSING\s*(\[[^\]]+\])?:?\s*/i, "");

export function Missing({ children }: { children: string }) {
  return <p className="missing-note"><span className="tag missing">Missing</span> {stripMissing(children)}</p>;
}

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* clipboard blocked: the text is still on screen to select */ }
  }
  return <button onClick={copy}>{copied ? "Copied" : label}</button>;
}
