import Link from "next/link";
import BuildTeaser from "./components/BuildTeaser";
import LiveMonth from "./components/LiveMonth";
import SiteNav from "./components/SiteNav";
import Statement from "./components/Statement";
import { Check } from "./components/icons";
import "./landing.css";

const AREAS = [
  {
    name: "Subscriptions",
    finds: "Services you've stopped using, two plans doing one job, free trials about to convert, and prices that crept up.",
    prepares: "The cancel page and a cancellation email, or a cheaper plan that fits how you use it.",
    ex: "HULU 877-8244858 CA  9.99",
  },
  {
    name: "Bills",
    finds: "Internet, phone and insurance that jumped when a promotional rate ended.",
    prepares: "A negotiation script with what you paid before and what others charge now.",
    ex: "COMCAST XFINITY  85.00, was 55.00",
  },
  {
    name: "Bank charges",
    finds: "The same charge twice, and fees a bank will often reverse if you ask.",
    prepares: "A dispute letter with its deadline, or a polite request to reverse the fee.",
    ex: "BEST BUY 00012345  129.99, twice",
  },
  {
    name: "Refunds owed",
    finds: "Price drops inside a store's adjustment window, and flights that were cancelled or moved.",
    prepares: "The claim, citing the store's policy or the US Department of Transportation refund rule.",
    ex: "UNITED UA 1532  cancelled, 412.40",
  },
  {
    name: "Settlements",
    finds: "Open class-action settlements that match things you bought.",
    prepares: "The official claim link and the proof it asks for. You file it yourself.",
    ex: "APPLE.COM/BILL  Landsheft v. Apple",
  },
];

const MODELS = [
  { name: "Nemotron 3.5 Lightning", id: "nvidia/Nemotron-3_5-Lightning", job: "Reads each email that passes the rules into plain facts, once.", when: "Every new email" },
  { name: "Nemotron 3 Nano", id: "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B", job: "Takes over when Lightning fails.", when: "Only on failure" },
  { name: "Nemotron 3 Super", id: "nvidia/nemotron-3-super-120b-a12b", job: "Reads plan and pricing pages into a list of plans.", when: "“Find cheaper”" },
  { name: "Nemotron 3 Ultra", id: "nvidia/Nemotron-3-Ultra-550b-a55b", job: "Fits those plans to how you use the service, and writes the cancellation email.", when: "When you click" },
  { name: "Nemotron 3.5 Super-VL", id: "nvidia/Nemotron-3.5-Super-VL", job: "Will read receipts sent as images and PDFs.", when: "Planned", planned: true },
];

const RULES = [
  { b: "Nothing happens without you.", p: "ClawBack never cancels, pays, sends or files anything. It prepares the request, and you send it." },
  { b: "It only reads.", p: "Email access is read-only. Your bank sign-in happens on Plaid's page, so ClawBack never sees your bank password." },
  { b: "Every find shows its working.", p: "The charges and emails it relied on, the rule behind the claim, and a link to that rule's official source." },
  { b: "Models don't make up links or numbers.", p: "Code does every date and every dollar. Links come from search results or checked pages, never from a model." },
];

export default function Home() {
  return (
    <div className="lp">
      <SiteNav current="home">
        <Link className="btn solid" href="/dashboard">Open the dashboard</Link>
      </SiteNav>

      <main id="content">
        <section className="lp-hero">
          <div className="wrap">
            <h1>Your statements are hiding money. <em>ClawBack finds it.</em></h1>
            <div className="lp-hero-grid">
              <div>
                <p className="lp-lead">
                  ClawBack reads your bank and email the way a careful friend would. It finds <b>subscriptions you&apos;ve
                  stopped using</b>, <b>bills that crept up</b>, <b>fees you can get reversed</b>, <b>refunds you&apos;re
                  owed</b> and <b>settlements you qualify for</b>. Then it writes the email, the script or the claim.
                  You make the final click.
                </p>
                <div className="lp-ctas">
                  <Link className="btn solid big" href="/dashboard">See it on a demo month</Link>
                  <a className="btn big" href="#how">How it works</a>
                </div>
                <p className="lp-note">A hackathon prototype. The dashboard opens on made-up demo data; no sign-up.</p>
              </div>
              <Statement />
            </div>
          </div>
        </section>

        <LiveMonth />

        <section className="lp-sec" id="finds" aria-labelledby="h-finds">
          <div className="wrap">
            <div className="lp-sec-head">
              <h2 id="h-finds">Five places money slips away.</h2>
              <p>One bank feed and one inbox cover all five. Each find comes with the request that gets the money back.</p>
            </div>
            <ol className="ledger">
              {AREAS.map((a, k) => (
                <li key={a.name}>
                  <span className="no">0{k + 1}</span>
                  <div>
                    <h3>{a.name}</h3>
                    <code className="ex">{a.ex}</code>
                  </div>
                  <p>{a.finds}</p>
                  <p className="prep"><b>ClawBack prepares</b>{a.prepares}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="lp-sec" id="how" aria-labelledby="h-how">
          <div className="wrap">
            <div className="lp-sec-head">
              <h2 id="h-how">Connect, read, prepare.</h2>
              <p>Cheap steps run on everything. Models only see what needs judgement, and code checks what they write.</p>
            </div>
            <ol className="flow">
              <li>
                <h3>Connect</h3>
                <p>Sign in to your email on your provider&apos;s own page: Gmail, Outlook, Yahoo, iCloud and others. Link your bank through Plaid, or upload a statement.</p>
                <div className="uses"><span className="tag">Nylas</span><span className="tag">Plaid</span><span className="tag">CSV upload</span></div>
              </li>
              <li>
                <h3>Read</h3>
                <p>Rules set aside email that can&apos;t matter. Nemotron 3.5 Lightning reads the rest into plain facts. Code finds the recurring charges and does all the date and money arithmetic.</p>
                <div className="uses"><span className="tag">Rules</span><span className="tag">Nemotron 3.5 Lightning</span><span className="tag">Code</span></div>
              </li>
              <li>
                <h3>Prepare</h3>
                <p>Each find gets its evidence and the rule behind it. Nemotron 3 Ultra writes the request, Tavily finds the right page, and you read it and send it.</p>
                <div className="uses"><span className="tag">Nemotron 3 Ultra</span><span className="tag">Tavily</span><span className="tag">You</span></div>
              </li>
            </ol>
          </div>
        </section>

        <section className="lp-sec" id="models" aria-labelledby="h-models">
          <div className="wrap">
            <div className="lp-sec-head">
              <h2 id="h-models">Small models read. Big models judge.</h2>
              <p>NVIDIA Nemotron models on Nebius Token Factory. If one fails, the next takes over, then plain code, so the app keeps working.</p>
            </div>
            <div className="table-scroll">
              <table className="models">
                <thead><tr><th>Model</th><th>Its job</th><th>Runs</th><th>Model ID</th></tr></thead>
                <tbody>
                  {MODELS.map((m) => (
                    <tr key={m.id} className={m.planned ? "planned" : undefined}>
                      <td>{m.name}</td><td>{m.job}</td><td>{m.when}</td><td><code>{m.id}</code></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="lp-after">
              Every call is logged with its model, time, tokens and cost, and the dashboard shows that log. Reading 15
              emails costs about $0.0005; one &ldquo;find cheaper&rdquo; click about $0.005.
            </p>
          </div>
        </section>

        <section className="lp-sec" id="trust" aria-labelledby="h-trust">
          <div className="wrap">
            <div className="lp-sec-head">
              <h2 id="h-trust">You make the final click.</h2>
              <p>Getting money back usually means sending something. ClawBack writes it; you decide whether it goes.</p>
            </div>
            <ul className="rules">
              {RULES.map((r) => (
                <li key={r.b}><Check /><div><b>{r.b}</b><p>{r.p}</p></div></li>
              ))}
            </ul>
          </div>
        </section>

        <section className="lp-sec" aria-label="Build status">
          <div className="wrap"><BuildTeaser /></div>
        </section>

        <section className="lp-end" aria-labelledby="h-end">
          <div className="wrap">
            <h2 id="h-end">See what a month looks like <em>with the highlighter on.</em></h2>
            <div className="lp-ctas">
              <Link className="btn solid big" href="/dashboard">Open the dashboard</Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="site-foot">
        <div className="wrap">
          <p>Built for the Nebius x NVIDIA Global AI Hackathon, 2026. NVIDIA Nemotron on Nebius Token Factory, Tavily for search, Nylas for email and Plaid for banks.</p>
          <p>ClawBack is a prototype and not financial or legal advice.</p>
        </div>
      </footer>
    </div>
  );
}
