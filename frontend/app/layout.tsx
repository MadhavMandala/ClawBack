import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./tailwind.css";
import "./globals.css";

// One face. Apple devices use their own system font (SF Pro) first; everywhere else gets Inter, which is close to
// it and has true tabular figures, so money lines up. Code and model IDs use the system monospace (globals.css).
const sans = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });

export const metadata: Metadata = {
  title: "ClawBack",
  applicationName: "ClawBack",
  description: "ClawBack reads your bank and email, finds money you're losing or owed, and prepares the request to get it back. You make the final click.",
  // Added to an iPhone's home screen, it opens full screen like an app (docs/MOBILE.md, stage 1).
  appleWebApp: { capable: true, title: "ClawBack", statusBarStyle: "default" },
  formatDetection: { telephone: false },
};

// viewportFit "cover" lets the installed app draw under the notch; globals.css pads for the safe areas.
// The browser's own bar matches the page in light and dark.
export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f6f2ea" },
    { media: "(prefers-color-scheme: dark)", color: "#15120e" },
  ],
  colorScheme: "light dark",
  viewportFit: "cover",
};

// Applies a light/dark choice saved by the nav's toggle (ThemeToggle.tsx) before the first paint, so a dark page
// never flashes white. With no saved choice the page follows the computer's setting.
const THEME_BOOT = `try{var t=localStorage.getItem("clawback.theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={sans.variable} suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: THEME_BOOT }} /></head>
      <body>{children}</body>
    </html>
  );
}
