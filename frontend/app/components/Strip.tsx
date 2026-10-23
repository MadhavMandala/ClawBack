"use client";

import { useEffect, useRef, useState } from "react";
import type { Subscription } from "../api";
import { money, reclaimable } from "../format";

// One bar for the whole month: each subscription is a slice sized by what it costs.
// The highlighted part of a slice is money ClawBack thinks you can get back.

const GAP = 2; // px of field showing between slices
const LABEL_PX_PER_CHAR = 7.4; // rough width of a 12.5px label character
const LABEL_PAD = 14;
const LABEL_LEFT = 9; // px from the slice's left edge

type Slice = { s: Subscription; mark: number; keep: number };

export default function Strip({ subs, onPick }: { subs: Subscription[]; onPick: (id: string) => void }) {
  const ref = useRef<HTMLUListElement>(null);
  const [width, setWidth] = useState(0);
  const [hover, setHover] = useState<{ id: string; x: number } | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);

  const slices: Slice[] = subs
    .filter((s) => s.monthly_cost > 0)
    .map((s) => ({ s, mark: reclaimable(s), keep: s.monthly_cost - reclaimable(s) }))
    // Money you can get back sits together on the left, biggest first.
    .sort((a, b) => b.mark - a.mark || b.s.monthly_cost - a.s.monthly_cost);

  const total = slices.reduce((t, x) => t + x.s.monthly_cost, 0);
  if (!total) return null;
  const usable = Math.max(0, width - GAP * (slices.length - 1));
  const hovered = hover && slices.find((x) => x.s.id === hover.id);

  return (
    <div className="strip-wrap">
      <ul ref={ref} className="strip" aria-label="Your monthly subscription spend, one slice per subscription">
        {slices.map(({ s, mark, keep }, i) => {
          const w = (s.monthly_cost / total) * usable;
          const fits = w >= s.merchant.length * LABEL_PX_PER_CHAR + LABEL_PAD;
          const markPx = (mark / s.monthly_cost) * w; // where the yellow ends, so the label can change colour there
          const label = `${s.merchant}, ${money(s.monthly_cost)} a month` + (mark > 0 ? `, could get back ${money(mark)}` : "");
          return (
            <li key={s.id} style={{ flexGrow: s.monthly_cost }}>
              <button
                className="slice"
                aria-label={label}
                onClick={() => onPick(s.id)}
                onPointerEnter={(e) => setHover({ id: s.id, x: sliceCenter(e.currentTarget, ref.current) })}
                onPointerLeave={() => setHover(null)}
                onFocus={(e) => setHover({ id: s.id, x: sliceCenter(e.currentTarget, ref.current) })}
                onBlur={() => setHover(null)}
              >
                {mark > 0 && (
                  <span className="part mark" style={{ flexGrow: mark, ["--i" as string]: i }}>
                    {fits && <span className="slice-label" style={{ left: LABEL_LEFT }}>{s.merchant}</span>}
                  </span>
                )}
                {keep > 0.005 && (
                  <span className="part keep" style={{ flexGrow: keep }}>
                    {fits && <span className="slice-label" style={{ left: LABEL_LEFT - (mark > 0 ? markPx : 0) }} aria-hidden>{s.merchant}</span>}
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
      {hovered && (
        <div className="tip" role="status" style={{ left: clamp(hover!.x, 90, width - 90) }}>
          <b>{hovered.s.merchant}</b> {money(hovered.s.monthly_cost)} a month
          {hovered.mark > 0 && <><br />Could get back {money(hovered.mark)}</>}
        </div>
      )}
    </div>
  );
}

function sliceCenter(el: HTMLElement, host: HTMLElement | null) {
  if (!host) return 0;
  const a = el.getBoundingClientRect();
  const b = host.getBoundingClientRect();
  return a.left - b.left + a.width / 2;
}

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
