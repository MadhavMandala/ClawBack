"use client";

import { useState } from "react";
import { call } from "../api";

const ADDRESS = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type Saved = { saved: boolean; provider: string | null; message: string };

// Saves the email as a draft in the person's own mailbox. ClawBack never sends it: they open it there and press send.
export default function SaveDraft({ path, subject, body, to }: { path: string; subject: string | null; body: string; to?: string | null }) {
  const [state, setState] = useState<{ busy: boolean; ok?: boolean; text?: string }>({ busy: false });
  async function save() {
    setState({ busy: true });
    try {
      const out = await call<Saved>(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subject, body, to: to && ADDRESS.test(to) ? to : null }),
      });
      setState({ busy: false, ok: true, text: out.message });
    } catch (e) {
      setState({ busy: false, ok: false, text: (e as Error).message });
    }
  }
  return (
    <>
      <button disabled={state.busy || state.ok} onClick={save}>{state.busy ? "Saving" : state.ok ? "Saved to Drafts" : "Save to my Drafts"}</button>
      {state.text && <p className="fine-print after">{state.text}</p>}
    </>
  );
}
