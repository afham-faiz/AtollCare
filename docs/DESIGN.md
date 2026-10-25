# Design system: sage, pine and clinical blue

The rules every screen follows. Tokens live in `web/src/styles/globals.css`; the few places that can't read CSS
variables (Recharts, Leaflet) use the same values from `web/src/lib/palette.ts`.

## Type

- **Red Hat Display** for headings and every measured number; **Red Hat Text** for everything you read; **Red Hat
  Mono** for codes (AC-PLFV, PA-JVT4). All variable weights from `next/font/google`.
- Numerals are the hero: the `.numeral` class (Display 300, tabular, `letter-spacing: -0.04em`). 88 px on the camera,
  56–64 px on cards, 24–40 px in lists. A live value keeps `min-width: 3ch` so it never jitters.
- Units sit beside the number in `.unit` (14 px, 500, `--ink-3`).
- Headings 400–450, never bold. Card titles are quiet: 15 px, 500, `--ink-2`. No uppercase labels anywhere.
- Body text 16 px; nothing lighter than `--ink-3` for text.

## Colour

- Canvas `#e6ede9` with a near-invisible fixed wash. Green is the brand and the patient (sage 100–700, pine for
  primary actions); teal is the live Presage signal (`--teal-glow` on the camera); blue is clinical data, links and
  the hospital.
- **Red is clinical urgency only:** NEWS2 ≥ 7, a single parameter scoring 3, apnoea, and the emergency call. Never a
  record button, a heart icon or a chart series. A failed upload or scan is caution amber.
- Series follow bedside monitors: heart rate `#4e7d5b`, breathing `#2e8e9a`, SpO₂ `#36668f`, NEWS2 in ink.
- An abnormal value keeps its numeral in ink; a dot and a word under it carry the colour.

## Shape and depth

- Radii: 12 (inputs, chips) · 18 (inner panels) · 28 (cards) · 40 (camera stage, sheets) · pills for every button,
  the nav and the docks. Inner radius = outer radius − padding.
- **Cards** (`.card`): lit and translucent, no blur, no grey hairline.
- **Glass** (`.glass`): only where something moves underneath: the top nav, docks, sheets, toasts, and the dark glass
  over the camera.
- Disabled is a `--well` fill with `--ink-3` text, never faded brand colour.

## Signals

- `Heartbeat` (`components/(vitals)/Signal.tsx`): a heart in soft rings that beats at the measured rate once Presage
  calls it steady, breathes slowly while acquiring, and rests otherwise.
- `Trace`: smooth Catmull-Rom curves (`lib/curves.ts`) for pulse and breathing waves; a dot marks the newest sample.
- `Bars`: recent readings as thin rounded bars, newest in the series colour.
- Charts: 1.5 px lines, no area fills, no axis lines, at most three dotted grid lines, a frosted pill tooltip.

## Motion

Enter 360 ms `cubic-bezier(.22,1,.36,1)` with an 8 px rise; press `scale(.97)`; no bounce. The heart's beat is
`60 / bpm` seconds. Everything stops under `prefers-reduced-motion`.

## Words

Sentence case. One coaching line, not a list. "Not yet recorded: SpO₂ · BP" instead of rows of dashes. Presage is
named once per measurement surface ("Measured by Presage · contactless").
