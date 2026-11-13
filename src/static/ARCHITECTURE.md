# Frontend Architecture

Vanilla HTML/CSS/JS, no build step. Bilingual (DE/EN), dark and high-contrast themes, designed at 360px first.

| File | Purpose |
|---|---|
| `index.html` | Page shell: header, persona chips, profile card, result card, conversation, input, citation card |
| `app.js` | State, event stream handling, lookup card, messages, citations |
| `style.css` | Theme tokens and components |
| `i18n.js` | `t(key, vars)` for interface text, `phrase(text)` for short labels sent by the server |
| `a11y-test.js` | Optional axe-core scan (`?a11y`) |

## Flow

1. Choosing a persona loads the profile and shows the result card.
2. Choosing a reading starts a fresh conversation and sends a `new_reading` turn. Switching persona with a reading chosen does the same for the new persona.
3. Typed questions send `question` turns in the same session.

## Components

- **Lookup card** — one step per source, with what was searched and found; collapses to a one-line summary when the answer arrives.
- **Answer** — Markdown rendered with `marked` after neutralising raw HTML. `[n]` becomes a button; the number stays on the line of the claim it follows.
- **Safety notice** — above the answer when a rule fired, showing the rule's text.
- **Sources list** — collapsed under each answer, grouped: safety, women like you, reference ranges, guidelines, best overall.
- **Citation card** — bottom sheet on a phone, centred card from 700px. Shows study, design and size, what matched, who was studied and where, the quoted passages, and a link. Focus moves into the card, Escape closes it, focus returns to the number.

## Layout

- Up to 600px: the whole page scrolls; header and input stay in place; persona and reading chips scroll sideways.
- From 700px: persona and result cards are single compact rows; only the conversation scrolls.

## Accessibility

An axe-core scan (WCAG 2.0–2.2 A/AA) of the finished page is clean in light, dark and high-contrast themes. White text sits on `--accent-strong`; blue text on light surfaces uses `--accent-text`.
