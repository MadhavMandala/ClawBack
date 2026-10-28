"use client";

import { useState } from "react";
import type { SpendGroup } from "../api";
import { money } from "../format";

// The month at a glance: what you pay in at most six groups. Each group is the part you keep (grey) then the part
// you could cut (green). Groups are told apart by the table beside the ring, not by colour.

const C = 130; // centre of the 260x260 viewBox
const R = 118; // outer radius
const r = 78; // inner radius
const TAU = Math.PI * 2;

type Arc = { label: string; part: "keep" | "mark"; a0: number; a1: number };

function point(a: number, rad: number) {
  return `${(C + rad * Math.sin(a)).toFixed(2)},${(C - rad * Math.cos(a)).toFixed(2)}`;
}

// A ring segment from angle a0 to a1 (radians, clockwise from 12 o'clock).
function segment(a0: number, a1: number) {
  const large = a1 - a0 > Math.PI ? 1 : 0;
  return `M${point(a0, R)} A${R},${R} 0 ${large} 1 ${point(a1, R)} L${point(a1, r)} A${r},${r} 0 ${large} 0 ${point(a0, r)} Z`;
}

function arcs(groups: SpendGroup[], total: number): Arc[] {
  const out: Arc[] = [];
  let a = 0;
  for (const g of groups) {
    const span = (g.monthly / total) * TAU;
    const keepEnd = a + ((g.monthly - g.could_cut) / total) * TAU;
    if (keepEnd - a > 1e-6) out.push({ label: g.label, part: "keep", a0: a, a1: keepEnd });
    if (a + span - keepEnd > 1e-6) out.push({ label: g.label, part: "mark", a0: keepEnd, a1: a + span });
    a += span;
  }
  // An SVG arc can't draw a full circle: split any arc of 360 degrees into two halves.
  return out.flatMap((x) => (x.a1 - x.a0 >= TAU - 1e-6 ? [{ ...x, a1: x.a0 + Math.PI }, { ...x, a0: x.a0 + Math.PI }] : [x]));
}

export default function Donut({ groups, selected, onSelect }: {
  groups: SpendGroup[];
  selected: string | null;
  onSelect: (label: string | null) => void;
}) {
  const [hover, setHover] = useState<string | null>(null);
  const total = groups.reduce((t, g) => t + g.monthly, 0);
  if (!groups.length || total <= 0) return null;
  const cut = groups.reduce((t, g) => t + g.could_cut, 0);
  const focus = hover ?? selected;
  const toggle = (label: string) => onSelect(selected === label ? null : label);

  return (
    <div className="donut">
      <div className="donut-left">
      <svg viewBox="0 0 260 260" className="donut-ring" role="img"
        aria-label={`${money(total)} a month in ${groups.length} groups, ${money(cut)} of it could be cut`}>
        {arcs(groups, total).map((x, i) => (
          <path key={i} d={segment(x.a0, x.a1)} className={`arc ${x.part}${focus && focus !== x.label ? " dim" : ""}`}
            onPointerEnter={() => setHover(x.label)} onPointerLeave={() => setHover(null)} onClick={() => toggle(x.label)} />
        ))}
        <text x={C} y={C - 6} textAnchor="middle" className="donut-total">{wholeDollars(total)}</text>
        <text x={C} y={C + 14} textAnchor="middle" className="donut-sub">a month</text>
      </svg>
      {cut > 0 && <p className="donut-cut"><span className="hl num">{wholeDollars(cut)}</span> could go</p>}
      </div>

      <table className="donut-table">
        <thead><tr><th>Group</th><th className="num">A month</th><th className="num">Could cut</th></tr></thead>
        <tbody>
          {groups.map((g) => (
            <tr key={g.label} className={focus === g.label ? "on" : undefined}>
              <td>
                <button className="donut-pick" aria-pressed={selected === g.label} onClick={() => toggle(g.label)}
                  onPointerEnter={() => setHover(g.label)} onPointerLeave={() => setHover(null)}
                  onFocus={() => setHover(g.label)} onBlur={() => setHover(null)}>
                  {g.label}
                </button>
              </td>
              <td className="num">{money(g.monthly)}</td>
              <td className="num">{g.could_cut > 0 ? <span className="hl">{money(g.could_cut)}</span> : <span className="nil">None found</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const wholeDollars = (n: number) => `$${Math.round(n).toLocaleString("en-US")}`;
