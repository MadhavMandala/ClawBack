# ClawBack design

**The idea:** a bank statement read late at night under a desk lamp, highlighter in hand. The highlighter marks
money you can get back, and nothing else. Everything else stays quiet so the yellow means something.

Two pages share one system:
- `/`, the front page. It explains ClawBack through one month of the demo user's statement, with margin notes.
- `/dashboard`, the app. One sentence about your month, the spend bar, findings grouped by what to do, the build
  status of every feature, and the model trace.

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
