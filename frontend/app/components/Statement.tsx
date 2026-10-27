// The front page's picture: one month of the demo user's bank statement, read with a highlighter.
// Every line and note comes from the demo data (backend/clawback/demo_data.py) and what the dashboard finds in it.
// The rule holds here too: yellow marks only money you can get back. When only part of a charge is reclaimable,
// the amount stays plain and the note highlights the part.

type Line = { d: string; t: string; a: string; mark?: boolean; note?: (hl: (s: string) => React.ReactNode) => React.ReactNode };

const LINES: Line[] = [
  { d: "10/02", t: "DOORDASH DASHPASS SAN FRANCISCO", a: "9.99" },
  { d: "10/04", t: "ORANGETHEORY FITNESS EDISON NJ", a: "169.00", mark: true, note: () => "No visits since Aug 25, says Google Maps. Cancel it." },
  { d: "10/05", t: "NETFLIX.COM 866-579-7172 CA", a: "17.99", mark: true, note: () => "Up from $15.49, and Netflix emailed “we miss you.”" },
  { d: "10/12", t: "SPOTIFY USA 877-778-1161", a: "11.99" },
  { d: "10/20", t: "HULU 877-8244858 CA", a: "9.99" },
  { d: "10/21", t: "BEST BUY 00012345 ATLANTA", a: "249.00", note: (hl) => <>Now $164.99 on bestbuy.com. Ask for {hl("$84.01")} back.</> },
  { d: "10/22", t: "KROGER #0412 ATLANTA GA", a: "48.00" },
];

export default function Statement() {
  let i = 0;
  return (
    <figure className="stmt" aria-label="An example bank statement and Google Maps Timeline, with the money ClawBack would flag highlighted">
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
        <span className="from">GOOGLE MAPS TIMELINE, ORANGETHEORY EDISON</span>
        <span className="subj">Three visits a week, then none after Aug 25.</span>
        <span className="n" style={{ ["--i" as string]: i }}>
          ClawBack writes the 30-day notice and sends it when you click Send.
        </span>
      </div>
    </figure>
  );
}
