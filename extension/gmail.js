// ClawBack for Gmail. Puts a small flag on inbox rows (and an open email) from a service where ClawBack found money.
// It reads one thing from Gmail's page: the sender's address, which Gmail keeps in an `email` attribute. The match
// happens here, in the browser. Nothing from Gmail is sent anywhere, and nothing in Gmail is changed or clicked.

(() => {
  const REFRESH = 60 * 1000;
  let flags = [];

  // --- Flags from the worker --------------------------------------------------------------------------------

  function load() {
    // After the extension is reloaded or removed, this copy of the script lives on in open Gmail tabs but can't
    // reach the extension any more. Stop quietly; reloading Gmail starts the new copy.
    if (!chrome.runtime?.id) return stop();
    try {
      chrome.runtime.sendMessage({ type: "flags" }, (res) => {
        if (chrome.runtime.lastError || !res) return;
        console.info(res.reason ? `ClawBack: no flags (${res.reason}).` : `ClawBack: ${(res.flags || []).length} flags.`);
        flags = res.flags || [];
        scan(true);
      });
    } catch {
      stop();
    }
  }

  let timer, observer;
  function stop() {
    clearInterval(timer);
    if (observer) observer.disconnect();
    console.info("ClawBack: the extension was reloaded. Reload Gmail to see flags.");
  }

  // An exact address first (a stand-in sender set for the demo), then the merchant's own domains.
  function flagFor(address) {
    const addr = (address || "").toLowerCase().trim();
    const domain = addr.split("@").pop();
    if (!addr || !domain) return null;
    return flags.find((f) => (f.addresses || []).includes(addr))
      || flags.find((f) => f.domains.some((d) => domain === d || domain.endsWith("." + d)))
      || null;
  }

  // --- Drawing ----------------------------------------------------------------------------------------------

  const FLAG_CSS = `
    :host { all: initial; display: inline-block; vertical-align: middle; margin: 0 6px 0 0; }
    button { all: unset; box-sizing: border-box; display: inline-flex; align-items: center; gap: 5px; height: 20px;
      padding: 0 7px 0 4px; border-radius: 3px; background: #07110d; color: #e8efe9; cursor: pointer;
      font: 600 11px/1 "Schibsted Grotesk", system-ui, -apple-system, "Segoe UI", sans-serif; letter-spacing: .01em; }
    button:focus-visible { outline: 2px solid #ffe14d; outline-offset: 1px; }
    svg { width: 14px; height: 14px; display: block; }`;

  const MARK = `<svg viewBox="0 0 28 28" aria-hidden="true"><path d="M6 21L12 6.5M12.5 23L18.5 8.5M19 21.5L24 9"
    stroke="#e8efe9" stroke-width="3.4" stroke-linecap="round" fill="none"/></svg>`;

  const CARD_CSS = `
    :host { all: initial; position: fixed; z-index: 2147483000; top: 0; left: 0; }
    .card { display: none; box-sizing: border-box; width: 300px; padding: 14px 16px; border-radius: 3px;
      background: #0e1d17; color: #e8efe9; border: 1px solid rgba(214, 232, 221, 0.2);
      font: 400 13px/1.45 "Schibsted Grotesk", system-ui, -apple-system, "Segoe UI", sans-serif; }
    .card.open { display: block; }
    b { display: block; font-weight: 700; font-size: 14px; margin: 0 0 6px; }
    p { margin: 0 0 6px; color: #9aaba1; }
    p.sum { color: #e8efe9; margin: 8px 0 10px; }
    mark { background: #ffe14d; color: #11170c; padding: 0 3px; border-radius: 2px; font-weight: 700; }
    a { color: #e8efe9; text-decoration: underline; text-underline-offset: 3px; font-weight: 600; }
    a:focus-visible { outline: 2px solid #ffe14d; outline-offset: 2px; }
    .by { display: block; margin-top: 10px; font-size: 11px; color: #6f8077; }`;

  const money = (n) => `$${n.toFixed(2)}`;
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  let cardHost, card, hideTimer, openFor;

  function ensureCard() {
    if (cardHost && document.body.contains(cardHost)) return;
    cardHost = document.createElement("clawback-card");
    const root = cardHost.attachShadow({ mode: "closed" });
    root.innerHTML = `<style>${CARD_CSS}</style><div class="card" role="dialog" aria-label="ClawBack"></div>`;
    card = root.querySelector(".card");
    card.addEventListener("mouseenter", () => clearTimeout(hideTimer));
    card.addEventListener("mouseleave", () => hideSoon());
    document.body.appendChild(cardHost);
  }

  function show(anchor, f) {
    ensureCard();
    clearTimeout(hideTimer);
    openFor = anchor;
    const sum = f.period === "month"
      ? `You could save <mark>${money(f.amount)}</mark> a month.`
      : `You could get <mark>${money(f.amount)}</mark> back.`;
    card.innerHTML = `<b>${esc(f.merchant)}</b>${f.lines.map((l) => `<p>${esc(l)}</p>`).join("")}
      <p class="sum">${sum}</p>
      <a href="${esc(f.link)}" target="_blank" rel="noopener">More info</a>
      <span class="by">From ClawBack. Matched on the sender's address, in your browser.</span>`;
    card.classList.add("open");
    const r = anchor.getBoundingClientRect();
    const left = Math.min(Math.max(8, r.left), window.innerWidth - 308);
    const below = r.bottom + 6 + card.offsetHeight < window.innerHeight;
    cardHost.style.left = `${left}px`;
    cardHost.style.top = `${below ? r.bottom + 6 : Math.max(8, r.top - 6 - card.offsetHeight)}px`;
  }

  function hide() {
    if (card) card.classList.remove("open");
    openFor = null;
  }

  function hideSoon() {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(hide, 150);
  }

  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && openFor) hide(); }, true);
  window.addEventListener("scroll", () => { if (openFor) hide(); }, true);

  function makeFlag(f) {
    const host = document.createElement("clawback-flag");
    host.dataset.target = f.target;
    const root = host.attachShadow({ mode: "closed" });
    root.innerHTML = `<style>${FLAG_CSS}</style><button type="button" aria-label="ClawBack: ${esc(f.merchant)}">${MARK}ClawBack</button>`;
    const btn = root.querySelector("button");
    btn.addEventListener("mouseenter", () => show(host, f));
    btn.addEventListener("mouseleave", hideSoon);
    btn.addEventListener("focus", () => show(host, f));
    btn.addEventListener("blur", hideSoon);
    // Keep Gmail from opening the email when the flag is clicked; a click toggles the card instead.
    for (const ev of ["mousedown", "mouseup"]) host.addEventListener(ev, (e) => e.stopPropagation());
    host.addEventListener("click", (e) => {
      e.stopPropagation();
      e.preventDefault();
      if (openFor === host) hide(); else show(host, f);
    });
    return host;
  }

  // --- Finding rows -----------------------------------------------------------------------------------------

  // Puts the flag for `address` at the start of `slot`, or takes away a stale one (Gmail reuses rows when paging).
  function place(slot, address) {
    if (!slot) return;
    const f = flagFor(address);
    const old = slot.querySelector(":scope > clawback-flag");
    if (old && (!f || old.dataset.target !== f.target)) old.remove();
    if (f && !(old && old.dataset.target === f.target)) slot.prepend(makeFlag(f));
  }

  function scan(all) {
    // Inbox and label lists: one row per thread; each sender's address is on a span[email]. A thread can list
    // several senders, so any of them can match. The flag goes before the subject, wherever this layout puts it
    // (the wide one-line layout and the narrow multi-line one differ), or before the sender as a last resort.
    // Rows are found from the sender spans, so a layout without tr.zA still works. Sender spans in an open email
    // (span.gD and the recipients) are handled below, not as rows.
    const rows = new Set(document.querySelectorAll("tr.zA"));
    for (const s of document.querySelectorAll("[role='main'] span[email]")) {
      if (s.closest(".gs, .adn, h3")) continue; // inside an open email
      const row = s.closest("tr, [role='row'], [role='listitem']");
      if (row) rows.add(row);
    }
    let matched = 0;
    for (const row of rows) {
      const senders = [...row.querySelectorAll("span[email]")].map((s) => s.getAttribute("email"));
      const match = senders.find((a) => flagFor(a)) || senders[0];
      const subject = row.querySelector(".bog");
      const slot = row.querySelector(".y6") || (subject && subject.parentElement) || row.querySelector(".xT")
        || (row.querySelector("span[email]") || {}).parentElement;
      if (flagFor(match)) matched += 1;
      place(slot, match);
    }
    if (all) {
      const senders = document.querySelectorAll("span[email]").length;
      console.info(`ClawBack: ${rows.size} rows, ${senders} sender addresses on the page, ${matched} rows flagged.`);
    }
    // An open email: the sender's name span.gD carries the address. The flag goes next to the subject.
    const opened = document.querySelector("span.gD[email]");
    const subject = document.querySelector("h2.hP");
    if (subject && subject.parentElement) {
      let slot = subject.parentElement.querySelector(":scope > clawback-slot");
      if (!slot) {
        slot = document.createElement("clawback-slot");
        slot.style.display = "inline-block";
        subject.insertAdjacentElement("afterend", slot);
      }
      place(slot, opened && opened.getAttribute("email"));
    }
    if (all && openFor && !document.contains(openFor)) hide();
  }

  let pending;
  observer = new MutationObserver(() => {
    clearTimeout(pending);
    pending = setTimeout(() => scan(false), 300);
  });
  observer.observe(document.body, { childList: true, subtree: true });

  load();
  timer = setInterval(load, REFRESH);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
})();
