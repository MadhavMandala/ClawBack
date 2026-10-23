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
  recovered_total: number;
  recovered_note: string;
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
};

export type ActionPrep = {
  title: string;
  summary: string;
  channel: "email" | "chat" | "phone" | "form" | "dispute" | "in_person";
  steps: string[];
  links: { label: string; url: string; verified: boolean }[];
  message: { to: string | null; subject: string | null; body: string } | null;
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
  merchant: string;
  you_save_per_month: number;
  next_charge: string | null;
  links: { label: string; url: string; verified: boolean }[];
  steps: string[];
  email: { subject: string; body: string; status: string };
  missing: string[];
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

export async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store", ...init });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.missing ?? body.detail ?? `${res.status} ${res.statusText}`);
  return body as T;
}
