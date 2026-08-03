# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

The desktop translation workspace has three persistent surfaces: source PDF/upload at upper left,
translation settings at lower left, and translated output/progress on the right. Keep the settings
surface compact. Preserve user-resizable horizontal and vertical splitters, render the selected
source PDF in the upload surface, and render only the translated PDF in the output surface. Route
page scrolling inside the active page so switching PDF/text/settings views never shifts the shell.
The horizontal splitter may expand the source PDF until settings collapses into a clickable summary
bar; expanding that bar restores the compact settings surface. Splitter pointer-down must never move
the layout without an actual drag. Hide settings scrollbars without disabling wheel/touch scrolling,
clip scrolling content inside the outer rounded card, and use custom rounded menus instead of native
square select popups. Use the short frameless desktop header with integrated Windows controls, and
label the local task area as `仓库`.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.
