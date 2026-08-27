# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

The current visual baseline is `frontend_tamplate/stitch_papertrans_ui_1/screen.png`, named
"Academic Precision" in its accompanying design notes. Preserve the existing five-module workspace
layout, but match this reference's restrained academic-tool styling: neutral paper/grey surfaces,
deep indigo accents, fine one-pixel outlines, compact spacing, low 4-8 px radii, and minimal shadow.
Use Inter for primary UI text, Geist for compact labels/headings, and JetBrains Mono only for terse
metadata. Do not reintroduce ambient gradients, glass effects, oversized pill cards, or Apple-like
large corner radii. Material Symbols is the shared icon language.

Motion follows the same restrained Academic Precision language. Navigation uses a shared sliding
selection surface and page changes use short directional translation. Workspace panel expansion
remains immediate; do not animate its grid resize or reveal. Use the shared
`cubic-bezier(.22, 1, .36, 1)` deceleration curve with 180-240 ms durations, keep travel distances
small, and always provide a `prefers-reduced-motion` fallback. Do not add spring, bounce, elastic,
or decorative looping motion.

The desktop translation workspace keeps text and PDF translation in one view. The left column stacks
text source, source PDF/upload, and translation settings; the right column stacks text translation
and translated PDF/progress. Do not bring back a PDF/text mode switch or a local-runtime badge.
Text translation uses the same provider settings as PDF translation. Keep its explicit compact
action in the source header, Ctrl+Enter shortcut, loading/success/failure states, selectable
read-only result field, and stale-result clearing when source text changes. Do not persist source
text or API credentials in the frontend.
The library is backed by the local FastAPI service and must show PDF and text history in separate
columns. Text tasks restore into the existing source/result panels; completed PDF tasks restore
the source PDF, translated PDF, and reading map into the dual reader. Folder actions stay available.
Render both the PDF and text library cards even when the entire library is empty; each card owns
its own concise no-task state instead of replacing the two-column structure with a global empty page.
PDF rows display the extracted paper title rather than the source filename. Text rows display the
backend-provided bounded source preview rather than a generic character-count label. Keep both on
one clipped line with ellipsis and a bounded tooltip; never load or persist full task bodies in the
frontend merely to build a library label.
Keep the two library columns equal in width and height. Their task lists scroll independently inside
the cards, with scrollbars visually hidden but wheel and touch scrolling preserved. Settings-page
scrolling follows the same hidden-scrollbar rule.
The frontend must never place restored source text, translations, paths, or API credentials in
localStorage or sessionStorage.
Keep every surface independently reachable through draggable splitters and clickable collapsed bars.
Render the selected source PDF only in the left PDF surface and translated PDF only on the right.
Both surfaces use the shared lazy-loaded PDF.js canvas reader. Keep separate page and zoom state,
with locally persisted user switches for page sync and zoom sync, while fitting each canvas
independently to its resizable panel. Mapping activation must navigate to the corresponding page
even when page sync is off. Do not reintroduce native `<embed>`/`iframe` PDF viewers.
PDF page, zoom, and action controls use Material Symbols inside fixed square buttons with a shared
icon baseline; do not use raw Unicode arrows or plus/minus glyphs. Ctrl+mouse-wheel over either PDF
changes the shared zoom while ordinary wheel scrolling remains local to that reader. The desktop
header baseline is 48 px (46 px in the compact-height media query). Result-folder and library
restore/open actions are icon-only with accessible labels and tooltips; do not add visible action
text back into those buttons.
Collapsed text bars keep their expand action vertically centered and omit empty-state filler copy.
Running PDF jobs must display truthful indeterminate motion, the backend-provided status message,
and elapsed time. Do not present named pipeline stages unless the backend actually reports stage
transitions.
PDF.js pages render a selectable transparent text layer over the canvas. The authenticated
`m7_reading_map_v1` response is fetched once per completed-job page. Resolve pointer-up positions
against its stable source/translation boxes without placing buttons over the text layer. A selected
flow highlights both readers without adding a paired-content dock that reduces the PDF reading area.
Track whether a linked flow was selected from the source or translation reader. Only the opposite
reader may auto-scroll, and only when its target geometry is outside the current viewport. Center
the target in both axes, use smooth scrolling normally, and honor `prefers-reduced-motion` with an
instant fallback.
Word/phrase selection is local-only and must remain inside one mapped paragraph. Normalize its
whitespace and cap selected text at 300 characters. A valid native selection and paragraph mapping
are mutually exclusive outcomes: single-click and drag selection never navigate, while only a
paragraph double-click may highlight and navigate the paired reader. Do not infer a word-level
bilingual alignment and do not call a translation provider
automatically. Holding Space while dragging pans the active PDF viewport; ordinary scrolling and
text selection must remain unchanged when Space is not held.
The source reader exposes “翻译所选” only for a valid same-paragraph selection and calls the
token-protected `/api/selection-translations` endpoint only from that explicit action. Place the
action next to the native selection and keep loading, failure, and result in a nearby page-surface
overlay; do not place selection summaries or actions in the viewer toolbar. Abort and clear stale
requests when selection/page/document context changes; keep results session-only and out of history.
Route page scrolling inside the active page so switching translation/settings views never shifts the shell.
Keep PDF.js render effects independent from transient parent callback identities and interaction
state. Debounce continuous container resizing, render canvas and text-layer content offscreen, and
commit both only after the render succeeds; never clear the visible page at render start.
M7.4 continuous reading must use a bounded virtual page window. Render only viewport-near pages,
release distant canvas and text-layer resources, derive toolbar state from the most-visible page,
and prevent observer/programmatic-scroll feedback loops. Preserve all M7.3 selection, mapping,
Space-pan, synchronization, and atomic-render guarantees during the migration.
The stage-one window is the current page plus two pages in each direction, so each reader owns at
most five mounted page surfaces. Keep lightweight proportional slots for distant pages so window
changes do not collapse scroll height. Reading maps now use a shared cancellable session cache for
the union of both ±2 page windows (at most ten pages), publish each completed page independently,
and evict stale pages. Continuous-scroll synchronization remains the next gate.
Linked paragraph scrolling must use stack-relative geometry derived from surface/root bounds, not a
surface `offsetTop` relative to its page slot. Keep the programmatic lock active across page travel
and paragraph centering. Ctrl-wheel previews with CSS around the cursor and commits PDF.js rendering
after 140 ms idle; never rebuild the page observer or call `scrollIntoView` on every zoom tick.
Continuous page sync broadcasts only an 80 ms settled most-visible-page candidate. Replace stale
candidates at page boundaries and cancel them before programmatic navigation; never let the target
reader echo intermediate pages. Keep sync-off scrolling independent and explicit mapping mandatory.
Keep the translation workspace mounted across top-level navigation. When library or settings is
active, hide that workspace with `visibility` and mark it `inert`; do not use conditional unmounting
or `display: none`, because both destroy reading progress or collapse PDF.js measurement geometry.
Hidden workspace controls must not remain focusable or receive pointer input.
Provider configuration is isolated by provider and persisted only through Tauri to Windows
Credential Manager. The settings-page buttons must use the controlled configuration dialog; never
reuse one provider's API key for another, persist keys in web storage or Python artifacts, or issue
an automatic network test on save. Keep the modal keyboard-contained, mask the secret by default,
and suppress WebView2's duplicate native password reveal control.
History deletion and storage cleanup must remain explicit, bounded actions with confirmation. Never
delete a PDF source or output when removing its library row. Text history deletion may remove only
the app-owned task directory after the backend atomically updates the library index. Cache cleanup
may target only `.papertrans/cache/`; temporary cleanup may target only unreferenced imports under
the managed uploads root. Disable destructive actions for running tasks, keep their modal state out
of browser persistence, and release superseded source registrations so orphan imports can be
reclaimed without unloading the preserved translation workspace.
Tauri owns close-to-tray behavior. The Rust close-request handler must hide the existing main
window by default, the tray must restore that same window, and an explicit tray quit or enabled
exit-on-close preference must follow the real application-exit path so the Python child is cleaned
up. The preference is non-sensitive and may use localStorage, but React must synchronize it to the
Rust state; do not emulate the tray with another browser window or leave multiple backends running.
Keep application-behavior switch rows title-only without explanatory subcopy. The titlebar must not
draw a separator before native window controls, and it must remain width-responsive so the close
button is fully visible at the narrowest Windows/DPI viewport.
Keep interaction feedback centralized in CSS. Native buttons share the global compositor-only
`scale`/`translate` press response; do not add per-button React state or pointer listeners for this
effect. Switches animate their track and move the thumb with `transform`, never by toggling a
non-interpolable flex alignment. Preserve `prefers-reduced-motion`, disabled states, and any
component-specific `transform` used for layout or PDF rendering.
The horizontal splitter may expand the source PDF until settings collapses into a clickable summary
bar; expanding that bar restores the compact settings surface. Splitter pointer-down must never move
the layout without an actual drag. Hide settings scrollbars without disabling wheel/touch scrolling,
clip scrolling content inside the outer card, and use custom low-radius menus instead of native
square select popups. Use the short frameless desktop header with integrated Windows controls,
native edge resizing and drag-to-restore behavior. Keep the three navigation items centered on the
window itself, independent of the brand and window-control widths, and label the local task area as
`仓库`. Tauri owns the frameless window and all native window behavior. Use
`data-tauri-drag-region` only on non-interactive titlebar surfaces and Tauri's window API for the
integrated controls. Do not add pywebview, WinForms, raw Win32 style mutation, synthetic non-client
messages, or transparent React resize overlays. Keep `decorations: false` and `resizable: true` so
Tauri provides native edge resizing, maximize/restore, drag-to-restore, and Windows corner states.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.
