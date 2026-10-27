// Types mirror backend/clawback/models.py. MISSING: generated from the OpenAPI schema instead of hand-copied.

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Flag = { kind: string; severity: "high" | "medium" | "info"; message: string; monthly_savings: number };

export type Subscription = {
  id: string;
  merchant: string;
  category: string;
  kind?: "subscription" | "bill";
  bill_category?: "internet" | "mobile" | "insurance" | "utility" | "gym" | null;
  cadence: string | null;
  amount: number | null;
  monthly_cost: number;
  last_charged: string | null;
  next_expected: string | null;
  charge_count: number;
  usage: { level: string; evidence: string[]; needs_checkin: boolean };
  value: { period_fee: number; uses: number; savings: number; net: number } | null;
  flags: Flag[];
  status: string;
  detected_from: string[];
};

export type Summary = {
  subscriptions: number;
  subscriptions_total?: number;
  bills?: number;
  bills_total?: number;
  monthly_total: number; // subscriptions + bills
  potential_monthly_savings: number;
  flagged: number;
  owed_total?: number; // one-time money from open findings
  owed_count?: number;
  recovered_total: number; // confirmed + self-reported
  recovered_confirmed?: number; // matched to a bank credit
  recovered_self_reported?: number;
  cancelled?: number; // subscriptions confirmed cancelled
  cancelled_monthly_savings?: number;
  recovered_note: string;
  spend_groups?: SpendGroup[]; // the dashboard donut: paying items in at most six groups
  trials?: TrialNote[]; // trials about to start charging, shown as a note under the donut
};

export type SpendGroup = {
  label: string;
  monthly: number;
  could_cut: number;
  items: { id: string; merchant: string; monthly: number; could_cut: number }[];
};

export type TrialNote = { id: string; merchant: string; amount: number; starts_on: string };

// GET /api/recovered: money back, confirmed from bank data or self-reported, newest first.
export type RecoveryEvent = {
  id: string;
  kind: "cancelled_subscription" | "refund" | "self_reported";
  status: "confirmed" | "self_reported";
  on: string;
  merchant: string;
  amount: number; // one-time money back (refunds); for a cancellation, what it has saved so far
  monthly: number | null; // a cancellation's monthly saving
  note: string;
  subscription_id: string | null;
  finding_id: string | null;
};
export type Recovered = {
  totals: { confirmed: number; self_reported: number; cancelled_monthly: number; cancelled_saved: number; cancelled_count: number };
  note: string;
  events: RecoveryEvent[];
};

export type Finding = {
  id: string;
  category: "charges" | "refunds" | "settlements";
  kind: "duplicate_charge" | "bank_fee" | "price_drop" | "flight_refund" | "flight_compensation" | "settlement";
  merchant: string;
  title: string;
  message: string;
  amount: number;
  amount_note: string | null;
  deadline: string | null;
  deadline_label: string | null;
  confidence: "high" | "medium" | "low";
  evidence: string[];
  rule: { name: string; summary: string; source_url: string } | null;
  status: "open" | "dismissed" | "done";
  found_on: string;
  // Price drops: what you paid next to today's price on the store's own site.
  price_check?: { store: string; item: string; paid: number; paid_on: string; now: number; url: string | null;
                  how: "live" | "simulated"; checked_on: string } | null;
};

// GET /api/showcase: the three workflows the dashboard leads with.
export type PriceWatch = {
  store: string; item: string; paid: number; paid_on: string; price_now: number; url: string | null;
  how: "live" | "simulated"; checked_on: string; deadline: string;
};
export type Showcase = {
  gym: { sub_id: string } | null;
  streaming: { sub_id: string } | null;
  price: { finding_id: string; watch?: undefined } | { watch: PriceWatch; finding_id?: undefined } | null;
};

export type ActionPrep = {
  title: string;
  summary: string;
  channel: "email" | "chat" | "phone" | "form" | "dispute" | "in_person";
  steps: string[];
  links: { label: string; url: string; verified: boolean }[];
  message: { to: string | null; subject: string | null; body: string; written_by?: string | null } | null;
  script: string[] | null;
  deadline: string | null;
  missing: string[];
};

export type TraceStep = {
  at: string;
  stage: string;
  engine: string;
  status: string;
  tier: string;
  ms: number;
  input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  cost_usd: number;
  note: string;
};

export type MissingItem = { id: string; area: string; priority: string; what: string; where: string; note: string };

export type Health = { ok: boolean; integrations: Record<string, boolean>; models: Record<string, string> };

export type CancelPrep = {
  subscription_id: string;
  merchant: string;
  you_save_per_month: number;
  next_charge: string | null;
  links: { label: string; url: string; verified: boolean }[];
  steps: string[];
  how_to: string[]; // the merchant's own steps only
  primary_link: { label: string; url: string; host: string; verified: boolean } | null;
  reminder_on: string | null; // the day to remind them, picked in code
  watch_after: string | null; // ClawBack checks the bank for a charge after this date
  // Only when the merchant's own page lists a cancellation address; most don't take email.
  email: { subject: string; body: string; status: string; to?: string | null; written_by?: string | null } | null;
  // A gym that takes written notice by email: where Send delivers. The server decides; in the demo it's yourself.
  send?: { to_shown: string; goes_to: string | null; test: boolean; from: string | null; connected: boolean } | null;
  // The user's rights line(s): their state's auto-renewal law when it applies, else federal ROSCA.
  rights?: { scope: "state" | "federal"; state: string | null; text: string; law: string; title: string; source_url: string; checked_on: string }[];
  missing: string[];
};

// GET /api/settings: the person's state, for the state auto-renewal line in cancel steps.
export type Settings = {
  state: string | null;
  state_name: string | null;
  state_rule: { law: string; title: string; user_right: string; source_url: string; checked_on: string } | null;
  states: { code: string; name: string; has_rule: boolean }[];
};

export type Alternatives = {
  hints: string[];
  options: { option: string; monthly_price: number | null; why: string; source_url: string }[];
  missing: string[];
};

export type Connection = {
  configured: boolean;
  connected: boolean;
  account?: string | null; // email address
  provider?: string | null; // google, microsoft, yahoo, icloud, imap
  institution?: string | null; // bank name
  last_sync: string | null;
  error: string | null;
  needs_reconnect?: boolean;
};

export type Connections = { mode: "demo" | "real"; email: Connection; plaid: Connection };

// GET /api/features: every planned feature and how far along it is (backend/clawback/features.py).
export type PhaseId = "planned" | "started" | "built" | "live";
export type Phase = { id: PhaseId; label: string; description: string };
export type Feature = {
  id: string;
  area: string;
  name: string;
  phase: PhaseId;
  summary: string;
  next: string | null;
  where: string;
  missing_id: string | null;
  priority: "P0" | "P1" | "P2" | null;
};
export type Features = { phases: Phase[]; areas: string[]; features: Feature[]; counts: Record<PhaseId, number>; updated: string };

// GET /api/me: this browser's session and what ClawBack holds for it. Never tokens or ids.
export type Me = {
  session: { kind: string; created_at: string | null; last_seen: string | null; deleted_after_idle_days: number | null };
  mode: "demo" | "real";
  connections: {
    email: { connected: boolean; account?: string | null; provider?: string | null; needs_reconnect?: boolean };
    plaid: { connected: boolean; institution?: string | null; needs_reconnect?: boolean };
  };
  counts: Record<"subscriptions" | "bills" | "findings" | "emails" | "transactions" | "gym_visits" | "alerts", number>;
  model_spend_today_usd: number;
  model_daily_limit_usd: number;
};

// GET /api/alerts: things a background run (new mail, the nightly check) found since you last looked.
export type Alert = {
  id: number; kind: "flag" | "finding"; ref: string; title: string; message: string; amount: number;
  created_at: string; seen: boolean;
};
export type Alerts = { alerts: Alert[]; unseen: number };

// POST .../email-draft: the email saved to the Drafts folder of the connected mailbox. ClawBack never sends it.
export type DraftResult = { saved: boolean; provider?: string | null; message: string };

/** Who wrote a letter: a Nemotron model id, or "template" when the model was off or its draft failed a check. */
export function writtenBy(id?: string | null): string | null {
  if (!id) return null;
  if (id === "template") return "Template";
  if (/ultra/i.test(id)) return "Written by Nemotron 3 Ultra";
  if (/super/i.test(id)) return "Written by Nemotron 3 Super";
  return `Written by ${id.replace(/^nvidia\//, "")}`;
}

// --- Session ------------------------------------------------------------------------------------------
// Each browser gets its own demo session (backend/clawback/sessions.py). The id lives in localStorage and goes
// to the API as the X-ClawBack-Session header: a header, not a cookie, because the API is on another domain.

const SESSION_KEY = "clawback.session";
export const SESSION_HEADER = "X-ClawBack-Session";

function storedSession(): string | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage.getItem(SESSION_KEY);
  } catch {
    return null; // private mode or blocked storage: the session lasts for this page load
  }
}

let memorySession: string | null = null; // used when localStorage is unavailable
let creating: Promise<string> | null = null; // one new session at a time, however many requests are waiting

async function createSession(): Promise<string> {
  const res = await fetch(`${API}/api/session`, { method: "POST", cache: "no-store" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok || typeof body.session_id !== "string") {
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
  }
  const id: string = body.session_id;
  memorySession = id;
  try {
    window.localStorage.setItem(SESSION_KEY, id);
  } catch {
    // keep it in memory only
  }
  return id;
}

/** This browser's session id, made on first use. `replacing`: an id the API just said has expired. */
export async function session(replacing?: string): Promise<string> {
  // Memory first: if saving to localStorage failed, an old stored id must not keep winning over the new one.
  const current = memorySession ?? storedSession();
  if (current && current !== replacing) return current;
  if (!creating) creating = createSession().finally(() => { creating = null; });
  return creating;
}

/** Forget this browser's session (after "Delete all my data"). The next request starts a fresh demo. */
export function forgetSession() {
  memorySession = null;
  try {
    window.localStorage.removeItem(SESSION_KEY);
  } catch {
    // nothing stored
  }
}

/** fetch() for the ClawBack API: adds the session header and, on "session expired", makes a new session and retries once. */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const send = (id: string) => {
    const headers = new Headers(init.headers);
    headers.set(SESSION_HEADER, id);
    return fetch(`${API}${path}`, { cache: "no-store", ...init, headers });
  };
  const id = await session();
  const res = await send(id);
  if (res.status !== 401) return res;
  const body = await res.clone().json().catch(() => ({}));
  if (body.detail !== "session expired") return res;
  return send(await session(id));
}

export async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await apiFetch(path, init);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.missing ?? body.detail ?? `${res.status} ${res.statusText}`);
  return body as T;
}
