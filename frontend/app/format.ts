import type { Flag, Subscription } from "./api";

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
export const money = (n: number) => usd.format(n);

// "2026-11-19" -> "Nov 19". Parsed as UTC so the day never shifts with the viewer's time zone.
export function shortDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" }).replace(" ", " "); // keep "Nov 19" on one line
}

// What ClawBack could get back on this subscription each month (never more than it costs).
export function reclaimable(s: Subscription): number {
  const best = Math.max(0, ...s.flags.map((f) => f.monthly_savings));
  return Math.min(best, s.monthly_cost);
}

const RANK: Record<string, number> = { high: 0, medium: 1, info: 2 };

export function leadFlag(s: Subscription): Flag | null {
  if (!s.flags.length) return null;
  return [...s.flags].sort((a, b) => RANK[a.severity] - RANK[b.severity] || b.monthly_savings - a.monthly_savings)[0];
}

export type GroupKey = "decide" | "bills" | "check" | "fine";

export function groupOf(s: Subscription): GroupKey {
  if (!s.flags.length && !(s.kind !== "bill" && s.usage.needs_checkin)) return "fine";
  if (s.kind === "bill") return "bills";
  if (s.flags.some((f) => f.severity === "high")) return "decide";
  return "check";
}

export function planLine(s: Subscription): string {
  const parts: string[] = [];
  if (s.cadence) parts.push(s.cadence[0].toUpperCase() + s.cadence.slice(1));
  const next = shortDate(s.next_expected);
  if (next) parts.push(`next charge ${next}`);
  return parts.join(", ");
}

export function sources(s: Subscription): string {
  const names = s.detected_from.map((d) => (d === "bank" ? "your bank charges" : d === "email" ? "your email" : d));
  return names.join(" and ");
}

// Backend text carries ISO dates ("2026-10-04: ..."); show them the way people write dates.
export const humanDates = (text: string) => text.replace(/\b(\d{4}-\d{2}-\d{2})\b/g, (d) => shortDate(d) ?? d);

// Whole days from today (the viewer's date) to an ISO date. Negative once it has passed.
export function daysLeft(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  const now = new Date();
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((Date.UTC(y, m - 1, d) - today) / 86_400_000);
}

export const isBill = (s: Subscription) => s.kind === "bill";
