// Types mirror backend/clawback/models.py. MISSING: generated from the OpenAPI schema instead of hand-copied.

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Flag = { kind: string; severity: "high" | "medium" | "info"; message: string; monthly_savings: number };

export type Subscription = {
  id: string;
  merchant: string;
  category: string;
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
  monthly_total: number;
  potential_monthly_savings: number;
  flagged: number;
  recovered_total: number;
  recovered_note: string;
};

export type TraceStep = {
  at: string;
  stage: string;
  engine: string;
  status: string;
  ms: number;
  input_tokens: number;
  output_tokens: number;
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

export async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store", ...init });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.missing ?? body.detail ?? `${res.status} ${res.statusText}`);
  return body as T;
}
