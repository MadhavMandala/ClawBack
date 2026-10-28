import type { Metadata } from "next";
import Link from "next/link";
import SiteNav from "../components/SiteNav";
import "./privacy.css";

// The same policy as docs/PRIVACY.md. Change both together.
// Fill these two in before the demo goes public.
const CONTACT = "[contact email]";
const REGION = "[server region]";
const UPDATED = "2026-10-23";

export const metadata: Metadata = {
  title: "Privacy policy | ClawBack",
  description: "What the ClawBack demo reads, what it stores, who processes it, and how to delete it.",
};

const PROVIDERS = [
  { name: "Nylas", href: "https://www.nylas.com/privacy-policy/", does: "Email sign-in, reading mail, saving drafts", gets: "Your mailbox access, as you grant it" },
  { name: "Plaid", href: "https://plaid.com/legal/#end-user-privacy-policy", does: "Bank sign-in and transactions", gets: "What you share on Plaid's page" },
  { name: "Nebius Token Factory", href: "https://docs.tokenfactory.nebius.com/legal/privacy-policy", does: "The AI models", gets: "Email text for the models, with Zero Data Retention" },
  { name: "Nebius AI Cloud", href: "https://docs.nebius.com/legal/privacy", does: "The server and its database", gets: "The database, on its disk" },
  { name: "Tavily", href: "https://www.tavily.com/privacy", does: "Web search", gets: "Merchant, bill type and product names in search text" },
  { name: "Vercel", href: "https://vercel.com/legal/privacy-policy", does: "Hosts the web pages", gets: "Standard request data" },
];

function Sec({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section className="pp-sec" id={id} aria-labelledby={`h-${id}`}>
      <h2 id={`h-${id}`}>{title}</h2>
      <div className="pp-body">{children}</div>
    </section>
  );
}

export default function Privacy() {
  return (
    <div className="pp">
      <SiteNav>
        <Link className="btn solid" href="/dashboard">Open the dashboard</Link>
      </SiteNav>

      <main id="content" className="wrap">
        <div className="pp-hero">
          <h1>Privacy policy. <em>What ClawBack reads, and what it never does.</em></h1>
          <p className="pp-meta">Last updated {UPDATED}.</p>
          <p className="pp-proto">
            <b>This is a prototype policy for a hackathon demo.</b> ClawBack is a student hackathon project, not a
            company. This page says plainly what the demo does with your data. It is not legal advice, and it will be
            reviewed before ClawBack is offered to anyone outside the demo.
          </p>
        </div>

        <div>
          <Sec id="short" title="The short version">
            <ul>
              <li>ClawBack reads your email and bank transactions to find money you are losing or owed.</li>
              <li>Email access is read-only. If you allow drafts, ClawBack can also save a draft in your mailbox. It sends a gym cancellation email only when you click Send, and, if you turn it on, a monthly recap to your own address. It never cancels, pays or files anything.</li>
              <li>If you upload a Google Maps Timeline file, ClawBack keeps only the dates you visited a gym it knows. The rest of the file is discarded as it&apos;s read.</li>
              <li>You sign in to your email and your bank on their own pages. ClawBack never sees those passwords.</li>
              <li>ClawBack stores the facts it pulls out of your email, never the email text itself.</li>
              <li>The AI models run on Nebius Token Factory with Zero Data Retention on, so prompts are not kept.</li>
              <li>Nobody sells your data, shows you ads with it, or trains a model on it.</li>
              <li>You can disconnect a source or delete all your data at any time.</li>
            </ul>
          </Sec>

          <Sec id="who" title="Who runs the demo">
            <p>
              The ClawBack team built the demo for the Nebius x NVIDIA Global AI Hackathon. The demo runs until judging
              ends in December 2026. Questions and deletion requests go to <b>{CONTACT}</b>.
            </p>
          </Sec>

          <Sec id="sessions" title="Demo sessions">
            <p>
              The demo has no accounts and no login. When you first open the dashboard, your browser gets a random
              session id. The browser sends it with every request, and the server keeps your data under it. The id is
              kept in your browser&apos;s storage on that device.
            </p>
            <ul>
              <li>The dashboard starts on a made-up demo month. Nothing in it is about a real person.</li>
              <li>Anyone who has your session id can see that session&apos;s data, so don&apos;t share it.</li>
              <li>Clearing your browser&apos;s site data starts a new session. The old session&apos;s data stays on the server until you use &ldquo;Delete my data&rdquo; or the demo closes.</li>
            </ul>
          </Sec>

          <Sec id="reads" title="What ClawBack reads">
            <h3>Email, through Nylas</h3>
            <p>
              ClawBack connects to Gmail, Outlook, Yahoo, iCloud and other inboxes through{" "}
              <a href="https://www.nylas.com">Nylas</a>, a third-party email service. Nylas processes your mail on
              ClawBack&apos;s behalf.
            </p>
            <ul>
              <li>You sign in on your email provider&apos;s own page. Nylas keeps the provider&apos;s access tokens. ClawBack keeps only a Nylas grant id, which works only together with ClawBack&apos;s own Nylas key.</li>
              <li>For iCloud and some other IMAP inboxes, you type an app password on Nylas&apos;s page. ClawBack never sees it, but it gives Nylas full access to that mailbox.</li>
              <li>ClawBack reads up to 150 messages from the last 180 days that look like receipts, renewals, trials, price changes or travel notices. For each one it uses the sender, subject, date and text.</li>
              <li><b>Drafts, if you allow them.</b> The sign-in page then also asks for permission to write drafts. ClawBack uses it only to save a draft you asked for, such as a cancellation email or a refund letter. For Gmail, Google&apos;s draft permission also allows sending mail. ClawBack never sends; you press send in your own mail app.</li>
            </ul>

            <h3>Bank transactions, through Plaid</h3>
            <p>
              ClawBack reads bank and card transactions through <a href="https://plaid.com">Plaid</a>. The demo only
              connects Plaid&apos;s test banks, with test logins.
            </p>
            <ul>
              <li>You sign in on Plaid&apos;s page. ClawBack never sees your bank username or password.</li>
              <li>ClawBack receives up to 180 days of transactions: the date, the description, the merchant name and the amount. It also gets the bank&apos;s name.</li>
            </ul>

            <h3>A statement file, if you upload one</h3>
            <p>You can upload a bank statement as a CSV file instead. ClawBack reads the date, description and amount columns.</p>
          </Sec>

          <Sec id="uses" title="What ClawBack does with it">
            <p>
              Plain code does most of the work: it finds recurring charges, does every date and dollar calculation, and
              checks each finding against a list of rules with official sources. Models only read text and write
              wording.
            </p>
            <h3>AI models on Nebius Token Factory</h3>
            <p>ClawBack uses NVIDIA Nemotron models on <a href="https://tokenfactory.nebius.com">Nebius Token Factory</a>.</p>
            <ul>
              <li>Rules first set aside email that can&apos;t matter. Nemotron 3.5 Lightning reads the rest, a few thousand characters of each, and returns facts such as the merchant, a price or the days left in a trial.</li>
              <li>Nemotron 3 Super reads public plan and pricing pages. Nemotron 3 Ultra compares them with a summary of how you use a service, and writes cancellation emails from facts the code worked out.</li>
              <li><b>Zero Data Retention is on</b> for ClawBack&apos;s Token Factory organization. Nebius does not store or log the prompts or the answers. Nebius does not use prompts to train models.</li>
            </ul>
            <h3>Web search with Tavily</h3>
            <p>
              ClawBack uses <a href="https://www.tavily.com">Tavily</a> to search the public web, for example to find a
              merchant&apos;s cancel page or current plans. Tavily receives the search text only. That text is built from
              a merchant name, a bill type (such as &ldquo;internet&rdquo;) or, for a price check, a product and store
              name. Tavily never receives your name, your email address, your account numbers or any email text.
            </p>
          </Sec>

          <Sec id="stores" title="What ClawBack stores, and where">
            <p>ClawBack keeps your session&apos;s data in one database on a server on Nebius AI Cloud, in {REGION}.</p>
            <p>It stores:</p>
            <ul>
              <li>the facts pulled out of each email (kind, merchant, amounts, dates), with the sender, subject and date;</li>
              <li>your transactions (date, description, amount);</li>
              <li>the subscriptions, bills and findings worked out from them;</li>
              <li>your choices: check-in answers, &ldquo;keep&rdquo;, &ldquo;dismiss&rdquo; and &ldquo;done&rdquo;, and the amounts you say you got back;</li>
              <li>the connection details: the Nylas grant id, the Plaid access token, the account name and the last sync time;</li>
              <li>a log of each step (which model or service ran, how long it took, the tokens and the cost). It never holds email text, tokens or keys.</li>
            </ul>
            <p>It does not store:</p>
            <ul>
              <li><b>the text of your emails.</b> Email text stays in the server&apos;s memory while it is read, and is never written to disk or to logs;</li>
              <li>your email or bank passwords, which ClawBack never sees.</li>
            </ul>
            <p>
              The Plaid access token and the Nylas grant id are <b>encrypted</b> in the database. The key that decrypts
              them stays on the server, outside the database and outside the code.
            </p>
            <p>
              The server also keeps short-lived request logs (time, address, path) to keep it running and secure. They
              don&apos;t contain email text.
            </p>
            <p>
              The front end runs on <a href="https://vercel.com">Vercel</a>, which sees standard request data such as
              your IP address and the pages you load. It doesn&apos;t receive your email or bank data.
            </p>
          </Sec>

          <Sec id="never" title="What ClawBack never does">
            <ul>
              <li>It never sells your data or shares it for advertising.</li>
              <li>It never uses your data to train or improve an AI model, ours or anyone else&apos;s.</li>
              <li>No person reads your email or transactions, unless you ask us to look at a problem with your session, or it is needed for security or the law.</li>
              <li>It never cancels, pays, disputes or files anything. It sends a gym cancellation email only when you click Send, and a monthly recap to you only if you turn it on. Everything else it prepares, and you make the final click.</li>
            </ul>
          </Sec>

          <Sec id="google" title="Google user data">
            <p className="pp-statement">
              ClawBack&apos;s use and transfer to any other app of information received from Google APIs will adhere to
              the{" "}
              <a href="https://developers.google.com/terms/api-services-user-data-policy">Google API Services User Data Policy</a>,
              including the Limited Use requirements.
            </p>
            <p>In practice, for Gmail data reached through Nylas:</p>
            <ul>
              <li>ClawBack uses it only to show you the subscriptions, bills and money owed that it finds, and to save drafts you ask for.</li>
              <li>It is shared only with the processors that provide those features (Nylas, and Nebius Token Factory for the models), never with anyone else.</li>
              <li>It is never used for ads, never sold, and never used to train AI models.</li>
              <li>People don&apos;t read it, except as described above.</li>
              <li>Email text is treated as untrusted and screened for hidden instructions before a model reads it.</li>
            </ul>
          </Sec>

          <Sec id="choices" title="Your choices">
            <ul>
              <li><b>Disconnect.</b> &ldquo;Disconnect&rdquo; removes the email or bank connection. ClawBack asks Nylas to delete the grant, or Plaid to remove the bank link, and drops that source&apos;s data.</li>
              <li><b>Delete my data.</b> &ldquo;Delete my data&rdquo; removes everything ClawBack holds for your session, including the saved connections, and asks Nylas and Plaid to drop them.</li>
              <li><b>Revoke access at the source.</b> You can also remove ClawBack&apos;s access in your Google, Microsoft or Yahoo account settings at any time.</li>
              <li><b>When the demo closes</b>, after judging ends in December 2026, we delete the server and its database.</li>
            </ul>
          </Sec>

          <Sec id="providers" title="Service providers">
            <div className="table-scroll">
              <table>
                <thead><tr><th>Provider</th><th>What it does for ClawBack</th><th>What it receives</th></tr></thead>
                <tbody>
                  {PROVIDERS.map((p) => (
                    <tr key={p.name}><td><a href={p.href}>{p.name}</a></td><td>{p.does}</td><td>{p.gets}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Sec>

          <Sec id="children" title="Children">
            <p>ClawBack is not meant for anyone under 18.</p>
          </Sec>

          <Sec id="changes" title="Changes">
            <p>If this policy changes, the date at the top changes too.</p>
          </Sec>

          <Sec id="contact" title="Contact">
            <p>Email <b>{CONTACT}</b> with questions or to ask us to delete a session&apos;s data.</p>
          </Sec>
        </div>
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
