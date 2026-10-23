# ClawBack design

**The idea:** a bank statement read late at night under a desk lamp, highlighter in hand. The highlighter marks
money you can get back, and nothing else. Everything else stays quiet so the yellow means something.

Four pages share one system:
- `/`, the front page. It explains ClawBack through one month of the demo user's statement, with margin notes.
- `/dashboard`, the app. One sentence about your month, the spend bar, findings grouped by what to do, the build
  status of every feature, and the model trace.
- `/settings`, "Your data": the session, connections, the state, what's stored, today's model use, and delete.
- `/privacy`, the prototype privacy policy.

References, picked on 2026-10-23 from [dark.design](https://www.dark.design/) and
[craftwork.design](https://craftwork.design/inspiration/websites):
- **Robinhood** (craftwork, Finance): a deep green-black ground, one acid accent, the product itself as the hero.
- **Cape Town Dam Levels Today** (dark.design): a dark data page with italic serif headlines, small monospaced
  labels, big numbers and thin annotation lines.

## Colour

| Token | Hex | Job |
|---|---|---|
| `--ground` | `#07110d` | Page ground |
| `--ground-2` | `#0a1712` | Bands on the ground (the month sentence, panels) |
| `--sheet` | `#0e1d17` | Tables, the statement, feature lists |
| `--sheet-2` / `--sheet-3` | `#12241c` / `#182d24` | An open row, and insets inside it (letters, rules) |
| `--ink` | `#e8efe9` | Text and the main buttons |
| `--muted` | `#9aaba1` | Secondary text (6.9:1 on `--sheet`) |
| `--faint` | `#6f8077` | Large or decorative text only |
| `--mark` | `#ffe14d` | **Highlighter. Only for money you can get back.** Never for buttons, headings or decoration |
| `--keep` | `#2c5646` | Money you're keeping, in the spend bar |

When only part of a charge is reclaimable (a bill that went up, a price drop), the charge stays plain and the
reclaimable part is highlighted where it's named.

State colours (`--loss`, `--check`, `--good`) only colour text that carries that meaning. Missing pieces use the
amber `--missing-bg` / `--missing-ink` pair. The build-status phases have their own four colours, from a faint
outline (planned) through amber (started) and green (built) to light green (tested live). They never use yellow.

## Type

Three faces, each with one job:
- **Newsreader** (serif, with optical sizes): headlines, section heads, the dashboard sentence and the margin notes
  on the statement. Italic for the second half of a headline and for notes.
- **Schibsted Grotesk**: everything you read or click in the interface. Money in table columns uses tabular figures;
  money inside a sentence doesn't.
- **IBM Plex Mono**: only where a bank or a terminal would print it: statement lines, model IDs, file paths.

Sentence case everywhere. Statement column heads are the one place with capitals, because statements print them
that way.

## Layout

- The front page is set like a ledger: rules between rows, numbered areas, no cards. Each section has a serif
  heading on the left and one plain sentence on the right.
- The dashboard leads with one plain sentence about your month, then the spend bar. There are no stat tiles.
- Findings are grouped by what you need to do. Each group is one table on one sheet, not a pile of cards.
- Each row gets one main action that matches its problem. In tables it's a quiet filled pill; a column of white
  pills would outshout the yellow. The white pill is for the page's main call to action only.
- Surfaces are nearly square (2-3px radius); controls are fully round. No shadows.

## Pieces added on 2026-10-23

- **Settings and privacy pages** use the privacy policy's ledger: a serif head on the left of each rule, plain text
  on the right, one column on small screens. Connections sit on one sheet with a button at the end of each row.
  "Delete all my data" is a red-outlined pill. It confirms in the page with "Yes, delete it" and "Keep it", never a
  browser dialog. The model-use meter is a thin bar in the built-phase green; it isn't money back, so it's never yellow.
- **First-visit guide** on the dashboard: one quiet band on `--ground-2` with three numbered lines (it's a demo month,
  open a yellow row, try it on your own) and "Got it". It shows once per browser and only in demo mode.
- **Alerts band**, "New since you last looked": a `--sheet` band with a 2px ink rule on the left, one line per alert,
  the amount highlighted only when it's money back, and "Mark as seen". Nothing else on the page uses a left rule.
- **Cancelled group and Money back table:** cancelled subscriptions get their own group at the end, out of the spend
  bar. Money back is a plain table: when, from, what happened, how it was checked, amount. "In your bank data" uses
  the green `ok` tag; "You told us" uses the neutral tag.
- **On a phone:** the app icon is the logo's three highlighter strokes in `--mark` on `--ground`, with a maskable
  Android version that keeps the strokes inside the safe zone. Installed, the app is full screen with a dark status
  bar; the nav and footer pad for the notch and home indicator. The install control on the settings page is one
  white pill on Android and a plain sentence on iPhone.
- **Who wrote it:** a letter or cancel email has a small neutral tag after its heading, "Written by Nemotron 3 Ultra"
  or "Template", so people can see which ones a model wrote.

## Motion

One moment per page:
- **Front page:** the pen goes down the statement. Each reclaimable amount is highlighted in turn and its margin
  note fades in after it.
- **Dashboard:** on first load the highlighter swipes across the money you can get back.

Everything else moves only when the user does something. `prefers-reduced-motion` turns both moments off.

## Things to avoid

These are what make a page look generated, from Anthropic's `frontend-design` skill, Impeccable and Taste Skill:
- three stat cards with a big number and a small label;
- identical rounded cards with a coloured left border;
- `A · B · C` meta strings joined with middle dots;
- tiny uppercase labels above headings;
- emoji or unicode arrows used as icons (draw an SVG in `components/icons.tsx` instead);
- gradients and glows;
- using yellow for anything that isn't reclaimable money.
