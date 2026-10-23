import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, Newsreader, Schibsted_Grotesk } from "next/font/google";
import "./globals.css";

// Three faces, each with one job:
// - Schibsted Grotesk for the interface (true tabular figures, so money lines up);
// - Newsreader for headlines and margin notes, like a newspaper writing about your month;
// - IBM Plex Mono only where a bank would print it: transaction lines, model IDs, file paths.
const sans = Schibsted_Grotesk({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const serif = Newsreader({ subsets: ["latin"], variable: "--font-serif", style: ["normal", "italic"], axes: ["opsz"], display: "swap" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], variable: "--font-mono", weight: ["400", "500"], display: "swap" });

export const metadata: Metadata = {
  title: "ClawBack",
  description: "ClawBack reads your bank and email, finds money you're losing or owed, and prepares the request to get it back. You make the final click.",
};

export const viewport: Viewport = { themeColor: "#07110D", colorScheme: "dark" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${serif.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
