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

export const Moon = ({ className }: P) => (
  <svg {...base} className={className}><path d="M13.2 9.6A5.6 5.6 0 0 1 6.4 2.8a5.6 5.6 0 1 0 6.8 6.8z" /></svg>
);

export const Sun = ({ className }: P) => (
  <svg {...base} className={className}>
    <circle cx="8" cy="8" r="2.9" />
    <path d="M8 1.5v1.3M8 13.2v1.3M1.5 8h1.3M13.2 8h1.3M3.4 3.4l.9.9M11.7 11.7l.9.9M3.4 12.6l.9-.9M11.7 4.3l.9-.9" />
  </svg>
);

// The app icon at nav size: three highlighter strokes on a dark rounded tile, the same as icon.svg and the
// phone icons, so the logo in the bar matches the one on the home screen.
export const Logo = ({ className }: P) => (
  <svg width="26" height="26" viewBox="0 0 28 28" fill="none" aria-hidden className={className}>
    <rect width="28" height="28" rx="7" fill="var(--logo-tile)" />
    <path d="M7.5 19.5L12 8.6M12.9 21.2L17.4 10.3M18.2 19.7L22 10.5" stroke="var(--brand)" strokeWidth="2.6" strokeLinecap="round" />
  </svg>
);
