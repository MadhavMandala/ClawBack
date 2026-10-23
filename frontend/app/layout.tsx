import type { Metadata, Viewport } from "next";
import { Schibsted_Grotesk } from "next/font/google";
import "./globals.css";

// One family for everything. It has true tabular figures, so money lines up in columns.
const sans = Schibsted_Grotesk({ subsets: ["latin"], variable: "--font-sans", display: "swap" });

export const metadata: Metadata = {
  title: "ClawBack",
  description: "Find the subscriptions you pay for but don't use, and get the money back.",
};

export const viewport: Viewport = { themeColor: "#0F3A2D" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={sans.variable}>
      <body>{children}</body>
    </html>
  );
}
