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

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg?.type === "flags") {
    flags().then(reply);
    return true; // reply comes later
  }
  if (msg?.type === "forget-cache") cache = null;
  return false;
});
