"use client";

import { useEffect, useState } from "react";

// "Add ClawBack to your phone": stage 1 of docs/MOBILE.md. Chrome on Android (and desktop) fires
// beforeinstallprompt, so we can offer a button; iPhone Safari has no such event, so we say where the menu is.

type InstallEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: "accepted" | "dismissed" }> };
type Mode = "installed" | "prompt" | "ios" | "other";

export default function InstallApp() {
  const [mode, setMode] = useState<Mode>("other");
  const [event, setEvent] = useState<InstallEvent | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    const standalone = window.matchMedia("(display-mode: standalone)").matches
      || (navigator as Navigator & { standalone?: boolean }).standalone === true;
    if (standalone) { setMode("installed"); return; }
    if (/iPhone|iPad|iPod/.test(navigator.userAgent)) setMode("ios");
    const onPrompt = (e: Event) => { e.preventDefault(); setEvent(e as InstallEvent); setMode("prompt"); };
    const onInstalled = () => { setDone(true); setMode("installed"); };
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  async function install() {
    if (!event) return;
    await event.prompt();
    const choice = await event.userChoice;
    setEvent(null);
    if (choice.outcome === "accepted") setDone(true);
  }

  if (mode === "installed") {
    return <p>{done ? "Installed. Open ClawBack from your home screen." : "You're using the installed app."}</p>;
  }
  if (mode === "prompt" && event) {
    return <p><button className="solid" onClick={install}>Install ClawBack</button></p>;
  }
  if (mode === "ios") {
    return <p>In Safari, tap <b>Share</b>, then <b>Add to Home Screen</b>.</p>;
  }
  return <p>Open this page on your phone. On Android, Chrome offers an install button here; on iPhone, use Safari&apos;s <b>Share</b> menu, then <b>Add to Home Screen</b>.</p>;
}
