// The only part that talks to ClawBack. It sends the read-only token, gets the flags, and passes the flags (never
// the token) to the Gmail script. Nothing from Gmail is sent anywhere.

const TTL = 60 * 1000;
let cache = null; // { at, flags }

async function flags() {
  if (cache && Date.now() - cache.at < TTL) return { flags: cache.flags };
  const { token, api } = await chrome.storage.local.get(["token", "api"]);
  if (!token || !api) return { flags: [], reason: "not-connected" };
  try {
    const res = await fetch(`${api}/api/email-flags`, { headers: { "X-ClawBack-Addon": token }, cache: "no-store" });
    if (res.status === 401) {
      await chrome.storage.local.remove(["token", "api"]);
      return { flags: [], reason: "token-revoked" };
    }
    if (!res.ok) return { flags: cache?.flags ?? [], reason: `server ${res.status}` };
    const body = await res.json();
    cache = { at: Date.now(), flags: body.flags ?? [] };
    return { flags: cache.flags };
  } catch {
    return { flags: cache?.flags ?? [], reason: "server unreachable" };
  }
}

// What each Gmail tab has on screen right now, for the toolbar badge and the popup. Kept in session storage, which
// survives the worker going to sleep and is cleared when Chrome closes.
async function setMatches(tabId, list) {
  const key = `tab-${tabId}`;
  const before = (await chrome.storage.session.get(key))[key] || [];
  await chrome.storage.session.set({ [key]: list });
  await chrome.action.setBadgeBackgroundColor({ tabId, color: "#07110d" });
  await chrome.action.setBadgeTextColor?.({ tabId, color: "#ffe14d" });
  await chrome.action.setBadgeText({ tabId, text: list.length ? String(list.length) : "" });
  // A new match opens the extension's window, where Chrome allows it (the Gmail window must be in front).
  const isNew = list.some((f) => !before.some((b) => b.target === f.target));
  if (isNew) chrome.action.openPopup?.().catch(() => {});
}

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (msg?.type === "flags") {
    flags().then(reply);
    return true; // reply comes later
  }
  if (msg?.type === "matches" && sender.tab?.id != null) {
    setMatches(sender.tab.id, Array.isArray(msg.flags) ? msg.flags : []);
    return false;
  }
  if (msg?.type === "forget-cache") cache = null;
  return false;
});

chrome.tabs.onRemoved.addListener((tabId) => chrome.storage.session.remove(`tab-${tabId}`));
