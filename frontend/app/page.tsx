import Link from "next/link";
import BuildTeaser from "./components/BuildTeaser";
import LiveMonth from "./components/LiveMonth";
import SiteNav from "./components/SiteNav";
import Statement from "./components/Statement";
import { Check } from "./components/icons";
import "./landing.css";

const AREAS = [
  {
    name: "A gym you stopped going to",
    finds: "Your Google Maps Timeline shows when you last went. No visit in 30 days, and fewer than two in 60, means you've stopped.",
    prepares: "The cancellation email with the notice your gym asks for. It goes from your own inbox when you click Send.",
    ex: "ORANGETHEORY FITNESS  169.00, last visit Aug 25",
  },
  {
    name: "Streaming you don't watch",
    finds: "The service emailed “we miss you,” and the price went up anyway.",
    prepares: "The service's own cancel page, one click away, and a check that the next charge doesn't come.",
    ex: "NETFLIX.COM  17.99, was 15.49",
  },
  {
    name: "A purchase that got cheaper",
    finds: "What you paid, from your bank and the order email, against today's price on the store's own site.",
    prepares: "The message to send the store, with its price adjustment policy and the deadline.",
    ex: "BEST BUY  249.00, now 164.99",
  },
];

const MODELS = [
  { name: "Nemotron 3.5 Lightning", id: "nvidia/Nemotron-3_5-Lightning", job: "Reads each email that passes the rules into plain facts, once.", when: "Every new email" },
  { name: "Nemotron 3 Nano", id: "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B", job: "Takes over when Lightning fails.", when: "Only on failure" },
  { name: "Nemotron 3 Super", id: "nvidia/nemotron-3-super-120b-a12b", job: "Reads plan and pricing pages into a list of plans.", when: "“Find cheaper”" },
  { name: "Nemotron 3 Ultra", id: "nvidia/Nemotron-3-Ultra-550b-a55b", job: "Writes the gym cancellation email and the price-drop request, and fits plans to how you use a service.", when: "When you click" },
  { name: "Nemotron 3.5 Super-VL", id: "nvidia/Nemotron-3.5-Super-VL", job: "Will read receipts sent as images and PDFs.", when: "Planned", planned: true },
];

const RULES = [
  { b: "Nothing happens without you.", p: "ClawBack never cancels, pays or files anything. It sends one email, a gym cancellation, only when you click Send. Everything else it prepares, and you send it." },
  { b: "It keeps only what it needs.", p: "From your email, the billing facts. From your Timeline, the days you went to a gym. Your bank sign-in happens on Plaid's page, so ClawBack never sees your bank password." },
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
                  ClawBack reads your bank, your email and your Google Maps Timeline the way a careful friend would.
                  It finds <b>the gym you stopped going to</b>, <b>the streaming service you don&apos;t watch</b> and{" "}
                  <b>the purchase that got cheaper</b>. Then it writes the email or the request. You make the final
                  click.
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
              <h2 id="h-finds">Three jobs, done start to finish.</h2>
              <p>Each one shows its evidence, then does the next step for you: the email, the cancel page or the request.</p>
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
                <p>Sign in to your email on your provider&apos;s own page. Link your bank through Plaid, or upload a statement. Upload your Google Maps Timeline export.</p>
                <div className="uses"><span className="tag">Nylas</span><span className="tag">Plaid</span><span className="tag">Google Maps Timeline</span></div>
              </li>
              <li>
                <h3>Read</h3>
                <p>Rules set aside email that can&apos;t matter. Nemotron 3.5 Lightning reads the rest into plain facts. Code finds the recurring charges and does all the date and money arithmetic.</p>
                <div className="uses"><span className="tag">Rules</span><span className="tag">Nemotron 3.5 Lightning</span><span className="tag">Code</span></div>
              </li>
              <li>
                <h3>Prepare</h3>
                <p>Each find gets its evidence and the rule behind it. Tavily checks today&apos;s price on the store&apos;s own site, Nemotron 3 Ultra writes the email, and you decide whether it goes.</p>
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
          <p><Link href="/privacy">Privacy policy</Link></p>
        </div>
      </footer>
    </div>
  );
}
