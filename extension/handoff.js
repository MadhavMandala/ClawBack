// Runs only on the ClawBack site. The Settings page hands over a read-only token (it lists flags and nothing
// else) and the API address. They go to chrome.storage.local; Gmail's page never sees them.

const API_ALLOWED = /^(http:\/\/localhost:8000|https:\/\/[a-z0-9-]+\.sslip\.io)$/;

window.addEventListener("message", (event) => {
  if (event.source !== window || event.origin !== window.location.origin) return;
  const m = event.data;
  if (!m || m.source !== "clawback") return;

  if (m.type === "addon-token" && typeof m.token === "string" && API_ALLOWED.test(m.api || "")) {
    chrome.storage.local.set({ token: m.token, api: m.api }, () => {
      chrome.runtime.sendMessage({ type: "forget-cache" });
      window.postMessage({ source: "clawback-addon", type: "addon-connected" }, window.location.origin);
    });
  } else if (m.type === "addon-disconnect") {
    chrome.storage.local.remove(["token", "api"], () => {
      chrome.runtime.sendMessage({ type: "forget-cache" });
      window.postMessage({ source: "clawback-addon", type: "addon-disconnected" }, window.location.origin);
    });
  } else if (m.type === "addon-ping") {
    chrome.storage.local.get(["token"], (s) => {
      window.postMessage({ source: "clawback-addon", type: "addon-here", connected: !!s.token }, window.location.origin);
    });
  }
});
