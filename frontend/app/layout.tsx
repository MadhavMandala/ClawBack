import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ClawBack",
  description: "Find the subscriptions you pay for but don't use.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
