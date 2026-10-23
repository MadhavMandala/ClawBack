// Connecting email (Nylas hosted sign-in) and a bank (Plaid Link). Shared by the dashboard and the settings page.

import { call } from "./api";

const PLAID_SCRIPT = "https://cdn.plaid.com/link/v2/stable/link-initialize.js";

type PlaidLink = { create: (o: Record<string, unknown>) => { open: () => void } };

function loadPlaid(): Promise<PlaidLink> {
  const w = window as unknown as { Plaid?: PlaidLink };
  if (w.Plaid) return Promise.resolve(w.Plaid);
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = PLAID_SCRIPT;
    s.onload = () => (w.Plaid ? resolve(w.Plaid) : reject(new Error("Plaid Link loaded but didn't start.")));
    s.onerror = () => reject(new Error("Couldn't load Plaid Link. Check your internet connection."));
    document.head.appendChild(s);
  });
}

/** Send the browser to the email provider's own sign-in page. It comes back to /dashboard?connected=email. */
export async function connectEmail(): Promise<void> {
  const out = await call<{ auth_url: string }>("/api/connect/email");
  if (out?.auth_url) window.location.assign(out.auth_url);
}

export type BankResult = { added_transactions: number; institution: string | null; pending: boolean };

/** Open Plaid Link. Resolves with the first pull once the bank is linked, or null if the person closed Link. */
export async function connectBank(): Promise<BankResult | null> {
  const { link_token } = await call<{ link_token: string }>("/api/connect/plaid/link-token", { method: "POST" });
  const Plaid = await loadPlaid();
  return new Promise((resolve, reject) => {
    Plaid.create({
      token: link_token,
      onSuccess: async (public_token: string, meta: { institution?: { name?: string } }) => {
        try {
          resolve(await call<BankResult>("/api/connect/plaid/exchange", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ public_token, institution: meta?.institution?.name ?? null }),
          }));
        } catch (e) {
          reject(e);
        }
      },
      onExit: (err: { display_message?: string; error_message?: string } | null) => {
        if (err) reject(new Error(err.display_message || err.error_message || "Bank connection didn't finish."));
        else resolve(null);
      },
    }).open();
  });
}

export function bankNotice(r: BankResult): string {
  return r.pending
    ? `${r.institution ?? "Your bank"} is connected. Plaid is still preparing transactions. Press Sync in a minute.`
    : `${r.institution ?? "Your bank"} is connected. Read ${r.added_transactions} transactions.`;
}
