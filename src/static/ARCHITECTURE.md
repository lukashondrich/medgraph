# Frontend Architecture

## Overview

Vanilla HTML/CSS/JS single-page app with no build step. Streams agent pipeline events via Server-Sent Events and renders real-time status badges as the LangGraph graph executes. Bilingual (DE/EN), WCAG 2.2 AA accessible, with dark mode and high-contrast support.

**Related docs:** [System overview](../../docs/system-overview.md) · [API backend](../api.py) · [Agents](../agents/ARCHITECTURE.md) · [State model](../models/ARCHITECTURE.md)

## File Structure

```
src/static/
  index.html      # Semantic HTML shell (ARIA roles, i18n data attributes)
  app.js           # SSE streaming, pipeline UI, patient gallery, state management
  style.css        # CSS custom properties for theming, responsive layout
  i18n.js          # DE/EN translation system (100+ keys)
  a11y-test.js     # Automated accessibility testing (axe-core)
```

Load order: `i18n.js` → `app.js` → `a11y-test.js`. The i18n module must load first because `app.js` calls `MedGraphI18n.t()` at init.

## Component Layout

```
┌─────────────────────────────────────────────┐
│  Header  [Local/Cloud] [DE] [☀] [◐]        │  header, model indicator, toolbar
├─────────────────────────────────────────────┤
│  Select a patient: [Maria 67F] [James 45M]  │  patient-bar (gallery buttons)
├─────────────────────────────────────────────┤
│  Maria Gonzalez  67F                     ✕   │  patient-card (shown after selection)
│  Type 2 diabetes with cardiovascular risk    │
│  [Diabetes] [Hypertension] [Metformin]       │
├─────────────────────────────────────────────┤
│                                              │
│  You                                         │
│  ┌────────────────────────────┐              │
│  │ Can I take ibuprofen?      │              │  chat-container
│  └────────────────────────────┘              │
│                                              │
│  Agent Pipeline                              │
│  ┌──────────────────────────────────┐        │
│  │ ✓ Routing 22s                    │  row 1 │  pipeline-card
│  │ ● Medication  ● Drug Check       │  row 2 │
│  │ ○ Synthesizer                    │  row 3 │
│  │ "Patient takes metformin..."     │  trace │
│  └──────────────────────────────────┘        │
│                                              │
│  medgraph                                    │
│  ┌────────────────────────────┐              │
│  │ Based on your profile...   │              │  assistant message
│  └────────────────────────────┘              │
│                                              │
├─────────────────────────────────────────────┤
│  [Ask a health question...] [🎤] [Send]      │  input-area
└─────────────────────────────────────────────┘
```

## State Management

All state lives in closure variables inside the `app.js` IIFE:

| Variable | Type | Purpose |
|----------|------|---------|
| `sessionId` | `string` | Current chat session (reset on patient change) |
| `isProcessing` | `bool` | Guards against double-submit during SSE stream |
| `selectedPatientId` | `string\|null` | Currently loaded patient |
| `isListening` | `bool` | Web Speech API recording state |
| `recognition` | `SpeechRecognition\|null` | Web Speech API instance |

No external state library. DOM is the source of truth for UI state (badge classes, `aria-pressed`, `style.display`).

## SSE Event → UI Mapping

The backend streams events as the LangGraph graph executes. `handleSSEEvent()` dispatches each event type to a specific UI update:

```
SSE Event                  → JS Handler                    → UI Effect
─────────────────────────────────────────────────────────────────────────
routing {status:processing}→ updatePipelineRouting()        → Router badge with spinner + timer starts
routing {agents,reasoning} → updatePipelineRouting()        → Router badge ✓, specialist badges appear,
                                                              reasoning typewriter-revealed at bottom
specialist {status:done}   → updatePipelineSpecialist()     → Badge spinner → ✓ checkmark
synthesizing {}            → updatePipelineSynthesizing()   → Synthesizer badge appears in row 3
response {content}         → appendAssistantMessage()       → Synthesizer ✓, chat bubble with markdown
error {message}            → appendAssistantMessage()       → Error shown as alert bubble
done {session_id}          → (updates sessionId)            → Stream cleanup
```

### Pipeline Visualization

The pipeline card renders a vertical 3-row layout mirroring the LangGraph execution:

```
Row 1: Router         [Thinking... 14s]  ← spinner + elapsed timer
Row 2: Specialists    [Symptom] [Med]    ← hidden until routing completes
Row 3: Synthesizer    [Synthesizing]     ← hidden until all specialists done
Trace: Reasoning      "Patient asks..."  ← typewriter revealed after routing
```

**Elapsed timer:** A `setInterval` (1s) updates the router badge's `.badge-timer` text. Stopped and frozen when the routing SSE event with `agents` arrives.

**Typewriter reveal:** Reasoning text appears 3 characters at a time (18ms interval). Respects `prefers-reduced-motion` — shows instantly if enabled.

**Local/cloud color:** The router badge gets a `local` (green) or `cloud` (blue) CSS class based on `model_source` from the SSE event. During the spinner phase, the initial class is inferred from the model indicator's current state (Ollama polling). The spinner inherits the badge's color.

## Theming

Four theme combinations via CSS custom properties on `:root`:

| `data-theme` | `data-contrast` | Result |
|--------------|-----------------|--------|
| `light` | (none) | Default light theme |
| `dark` | (none) | Dark theme |
| `light` | `high` | High contrast light |
| `dark` | `high` | High contrast dark |

Theme is persisted in `localStorage` (`medgraph-theme`, `medgraph-contrast`). On first visit, respects `prefers-color-scheme: dark`.

Key design tokens: `--bg`, `--surface`, `--text`, `--accent`, `--accent-light`, `--border`, `--user-bubble`, `--assistant-bubble`, `--safety-bg`.

## Internationalization (i18n)

`MedGraphI18n` is a self-contained module exposing `t(key)`, `setLanguage(lang)`, `applyTranslations()`, `getLang()`.

**How it works:**
1. HTML elements use `data-i18n="key"` (textContent), `data-i18n-html="key"` (innerHTML), `data-i18n-placeholder="key"`, or `data-i18n-aria="key"` (aria-label)
2. `applyTranslations()` scans the DOM and applies all translations
3. Dynamic content (pipeline badges, chat messages) uses `t(key)` directly in JS
4. Language persisted in `localStorage` (`medgraph-lang`), defaults to `en`

**Adding a translation key:**
1. Add the key to both `en` and `de` objects in `i18n.js`
2. Use `t("yourKey")` in JS or `data-i18n="yourKey"` in HTML

## Accessibility

WCAG 2.2 AA compliance:

| Feature | Implementation |
|---------|---------------|
| Skip link | `.skip-link` — hidden until focused, jumps to `#chatContainer` |
| Screen reader announcements | `#srAnnouncements` — `aria-live="assertive"`, updated via `announce()` |
| Touch targets | All interactive elements ≥ 44px (`min-height: 2.75rem`) |
| Focus indicators | `:focus-visible` with 3px `var(--focus-ring)` outline |
| Reduced motion | `@media (prefers-reduced-motion: reduce)` disables animations; typewriter shows text instantly |
| ARIA roles | Pipeline badges: `role="status"` + `aria-label`; patient buttons: `aria-pressed`; chat: `aria-live="polite"` |
| Color contrast | All text meets 4.5:1 ratio; dark mode button uses `#3a5cd0` for white text contrast |
| Semantic HTML | `<header>`, `<main>`, `<footer>`, `<article>`, `<nav>`, `<section>` |

**Automated testing:** `a11y-test.js` runs axe-core checks on page load (dev only).

## Speech Recognition

Uses the Web Speech API (`SpeechRecognition` / `webkitSpeechRecognition`):

- Single-utterance mode (`continuous: false`)
- Language synced with i18n (`en-US` / `de-DE`)
- Transcript inserted into the message input (not auto-submitted)
- Graceful degradation: mic button disabled with tooltip if API unavailable
- Visual feedback: `.listening` class triggers red pulse animation on mic button

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| Vanilla JS, no framework | No build step, fast load, easy to read. The app is a single interactive page — React/Vue would be overhead. |
| CSS custom properties for theming | Four theme combos from one set of tokens. No preprocessor needed. |
| SSE via `ReadableStream` | `EventSource` doesn't support POST. Manual SSE parsing via `response.body.getReader()` gives full control. |
| `marked.js` via CDN | Markdown rendering for assistant responses. Single external dependency, loaded from CDN to avoid bundling. |
| IIFE wrapper | All state and functions scoped inside `(function(){})()` to avoid global namespace pollution. |
| DOM as state | No virtual DOM or reactive state. Pipeline badge classes (`processing` → `done`) and `style.display` toggles are the state. Simple for this complexity level. |
