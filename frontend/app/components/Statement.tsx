// The front page's picture: one month of the demo user's bank statement, read with a highlighter.
// Every line and note comes from the demo data (backend/clawback/demo_data.py) and what the dashboard finds in it.
// The rule holds here too: yellow marks only money you can get back. When only part of a charge is reclaimable,
// the amount stays plain and the note highlights the part.

type Line = { d: string; t: string; a: string; mark?: boolean; note?: (hl: (s: string) => React.ReactNode) => React.ReactNode };

const LINES: Line[] = [
  { d: "10/02", t: "DOORDASH DASHPASS SAN FRANCISCO", a: "9.99", mark: true, note: () => "Saved you $2.99 this month, so it cost you $7." },
  { d: "10/05", t: "NETFLIX.COM 866-579-7172 CA", a: "17.99" },
  { d: "10/06", t: "OVERDRAFT ITEM FEE", a: "35.00", mark: true, note: () => "Banks often waive a first one. Ask." },
  { d: "10/09", t: "COMCAST XFINITY 800-266-2278", a: "85.00", note: (hl) => <>Up {hl("$30")} a month since the promo ended. Ask for the old rate.</> },
  { d: "10/12", t: "SPOTIFY USA 877-778-1161", a: "11.99" },
  { d: "10/14", t: "BEST BUY 00012345 ATLANTA", a: "129.99" },
  { d: "10/14", t: "BEST BUY 00012345 ATLANTA", a: "129.99", mark: true, note: () => "The same charge twice. Dispute it." },
  { d: "10/17", t: "TARGET 00011111 ATLANTA", a: "199.99", note: (hl) => <>Now {hl("$30")} cheaper. Claim it by Oct 31.</> },
  { d: "10/20", t: "HULU 877-8244858 CA", a: "9.99", mark: true, note: () => "Hulu emailed “we miss you.” Cancel?" },
  { d: "10/22", t: "KROGER #0412 ATLANTA GA", a: "48.00" },
];

export default function Statement() {
  let i = 0;
  return (
    <figure className="stmt" aria-label="An example bank statement with the money ClawBack would flag highlighted">
      <div className="stmt-top">
        <b>First Platypus Bank, checking</b>
        <span>OCT 01 TO OCT 22, 2026</span>
      </div>
      <div className="stmt-cols" aria-hidden><span>DATE</span><span>DESCRIPTION</span><span>AMOUNT</span><span /></div>
      <ol className="stmt-rows">
        {LINES.map((l, k) => {
          const n = l.note ? i++ : 0;
          const step = { ["--i" as string]: n };
          const hl = (s: string) => <span className="hl" style={step}>{s}</span>;
          return (
            <li key={k} className={`stmt-row${l.note ? "" : " quiet"}`}>
              <span className="d">{l.d}</span>
              <span className="t">{l.t}</span>
              <span className="a">{l.mark ? hl(l.a) : l.a}</span>
              {l.note && <span className="n" style={step}>{l.note(hl)}</span>}
            </li>
          );
        })}
      </ol>
      <div className="inbox">
        <span className="from">FROM United Airlines, OCT 19</span>
        <span className="subj">Your flight UA 1532 on Nov 4 has been cancelled</span>
        <span className="n" style={{ ["--i" as string]: i }}>
          A cash refund is owed: <span className="hl" style={{ ["--i" as string]: i }}>$412.40</span>
        </span>
      </div>
    </figure>
  );
}
