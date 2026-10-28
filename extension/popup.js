// The toolbar window: what ClawBack found among the emails on screen in this Gmail tab.

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const money = (n) => `$${n.toFixed(2)}`;

(async () => {
  const list = document.getElementById("list");
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const key = `tab-${tab?.id}`;
  const found = (await chrome.storage.session.get(key))[key] || [];
  const { token } = await chrome.storage.local.get(["token"]);

  if (found.length) {
    document.getElementById("title").textContent =
      `ClawBack found ${found.length === 1 ? "an email" : `${found.length} emails`} worth a look`;
    list.innerHTML = found.map((f) => `<div class="item"><b>${esc(f.merchant)}</b>
      ${f.lines.map((l) => `<p>${esc(l)}</p>`).join("")}
      <p class="sum">${f.period === "month" ? `You could save <mark>${money(f.amount)}</mark> a month.` : `You could get <mark>${money(f.amount)}</mark> back.`}</p>
      <a href="${esc(f.link)}" target="_blank" rel="noopener">More info</a></div>`).join("");
  } else if (!token) {
    list.innerHTML = `<p class="empty">Not connected. Open ClawBack's settings page and click Connect on the Gmail add-on row.</p>`;
  } else if (!tab?.url?.startsWith("https://mail.google.com/")) {
    list.innerHTML = `<p class="empty">Connected. Open Gmail to see which emails ClawBack flags.</p>`;
  } else {
    list.innerHTML = `<p class="empty">Nothing flagged among the emails on screen. Emails from services where ClawBack found money get a flag.</p>`;
  }
})();
