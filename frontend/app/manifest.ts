import type { MetadataRoute } from "next";

// The web app manifest: what a phone needs to install ClawBack on the home screen and open it full screen,
// like an app. Stage 1 of the phone app plan in docs/MOBILE.md. Icons are drawn from the logo in
// components/icons.tsx (public/icons/*.png, app/apple-icon.png for iOS).
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "ClawBack",
    short_name: "ClawBack",
    description: "Finds money you're losing or owed in your bank and email, and prepares the request to get it back.",
    start_url: "/dashboard",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#f6f2ea",
    theme_color: "#f6f2ea",
    categories: ["finance", "productivity"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Owed to you", url: "/dashboard#owed" },
      { name: "Money back", url: "/dashboard#money-back" },
      { name: "Your data", url: "/settings" },
    ],
  };
}
