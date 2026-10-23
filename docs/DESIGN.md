# ClawBack design

**The idea:** a bank statement someone has gone through with a yellow highlighter. The highlighter marks
money you can get back, and nothing else. Everything else stays quiet so the yellow means something.

## Colour

| Token | Hex | Job |
|---|---|---|
| `--paper` | `#f1f1ec` | Page ground |
| `--sheet` | `#ffffff` | Tables and panels, one tone step up from the ground |
| `--ink` | `#16211c` | Text and solid buttons |
| `--muted` | `#56615b` | Secondary text (5.7:1 on paper) |
| `--field` | `#0f3a2d` | Bank-green header band |
| `--mark` | `#ffe14d` | **Highlighter. Only for money you can get back.** Never for buttons, headings or decoration |
| `--keep` | `#6b9a87` | Money you're keeping, in the spend bar (4:1 on the field) |

State colours (`--loss`, `--check`) only colour text that carries that meaning. Missing pieces use the amber
`--missing-bg` / `--missing-ink` pair, so "not built yet" always looks the same.

## Type

One family: **Schibsted Grotesk** (loaded with `next/font`). It has tabular figures, so every money column
uses `font-variant-numeric: tabular-nums`. Five sizes only: 13, 14, 15, 18 and the header sentence (26–38px).
Sentence case everywhere. No all-caps labels and no monospace, except model IDs in the trace table.

## Layout

- The header leads with one plain sentence about your month, then the spend bar. There are no stat tiles.
- Subscriptions are grouped by what you need to do: **Needs a decision**, **Worth a look**, **Looks fine**.
  Each group is one table with a single sheet behind it, not a pile of cards.
- Each row gets one primary action that matches its problem. Everything else sits in the row's detail.
- Paper surfaces are square (2px radius); controls are fully round. No shadows except the tooltip.

## Motion

There's one moment: on first load, the highlighter swipes across the money you can get back. Everything else
moves only when the user does something. `prefers-reduced-motion` turns the swipe off.

## Things to avoid

These are what make a page look generated, from Anthropic's `frontend-design` skill, Impeccable and Taste Skill:
- three stat cards with a big number and a small label;
- identical rounded cards with a coloured left border;
- `A · B · C` meta strings joined with middle dots;
- tiny uppercase labels above headings;
- emoji or unicode arrows used as icons (draw an SVG in `components/icons.tsx` instead);
- gradients and glows;
- using yellow for anything that isn't reclaimable money.
