// Drawn icons, one stroke weight. No emoji or unicode glyphs stand in for icons.

type P = { className?: string };
const base = { width: 16, height: 16, viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: 1.75, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };

export const Chevron = ({ className }: P) => (
  <svg {...base} className={className}><path d="M4 6l4 4 4-4" /></svg>
);

export const Check = ({ className }: P) => (
  <svg {...base} className={className}><path d="M3.5 8.5l3 3 6-7" /></svg>
);

export const Close = ({ className }: P) => (
  <svg {...base} className={className}><path d="M4 4l8 8M12 4l-8 8" /></svg>
);

export const External = ({ className }: P) => (
  <svg {...base} className={className}><path d="M9 3h4v4M13 3L7.5 8.5M11 9.5V13H3V5h3.5" /></svg>
);

// Three highlighter strokes: the mark ClawBack leaves on money you can get back.
export const Logo = ({ className }: P) => (
  <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden className={className}>
    <path d="M6 21L12 6.5M12.5 23L18.5 8.5M19 21.5L24 9" stroke="var(--mark)" strokeWidth="3.4" strokeLinecap="round" />
  </svg>
);
