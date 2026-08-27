import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const app = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");
const api = await readFile(new URL("../src/api.ts", import.meta.url), "utf8");
const desktop = await readFile(new URL("../src/desktop.ts", import.meta.url), "utf8");
const viewer = await readFile(new URL("../src/PdfViewer.tsx", import.meta.url), "utf8");
const styles = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");
const types = await readFile(new URL("../src/types.ts", import.meta.url), "utf8");

test("PDF controls use aligned icon glyphs and Ctrl-wheel zoom", () => {
  assert.match(viewer, /material-symbols-outlined/);
  assert.match(viewer, /event\.ctrlKey/);
  assert.match(viewer, /passive:\s*false/);
  assert.doesNotMatch(viewer, />[‹›−＋]</);
});

test("result and library actions are compact icon-only controls", () => {
  assert.match(app, /aria-label="打开任务文件夹"/);
  assert.match(app, /aria-label=\{task\.kind === "pdf" \? "打开任务文件夹" : "恢复文本任务"\}/);
  assert.doesNotMatch(app, /<strong>\{job\.status === "completed" \? "翻译完成"/);
  assert.doesNotMatch(app, /\{task\.kind === "text" \? "恢复" : "打开文件夹"\}/);
});

test("shared icon and header metrics enforce a compact baseline", () => {
  assert.match(styles, /\.material-symbols-outlined\s*\{[^}]*line-height:\s*1/s);
  assert.match(styles, /\.app-header\s*\{[^}]*height:\s*48px/s);
  assert.match(styles, /\.library-action\s*\{[^}]*width:\s*36px/s);
});

test("navigation keeps the translation workspace mounted without making it interactive", () => {
  assert.doesNotMatch(app, /\{view === "translate" && \(/);
  assert.match(app, /view === "translate" \? "view-active" : "view-preserved"/);
  assert.match(app, /aria-hidden=\{view !== "translate"\}/);
  assert.match(app, /inert=\{view !== "translate"\}/);
  assert.match(styles, /\.translate-page\.view-preserved\s*\{[^}]*visibility:\s*hidden/s);
  assert.match(styles, /\.translate-page\.view-preserved\s*\{[^}]*pointer-events:\s*none/s);
  assert.doesNotMatch(styles, /\.translate-page\.view-preserved\s*\{[^}]*display:\s*none/s);
});

test("provider settings persist securely and use compact status indicators", () => {
  assert.match(app, /function ProviderConfigDialog/);
  assert.match(app, /role="dialog"/);
  assert.match(app, /aria-modal="true"/);
  assert.match(app, /inert=\{configuringProvider !== null \|\| pendingConfirmation !== null\}/);
  assert.match(app, /event\.key !== "Tab"/);
  assert.match(app, /onClick=\{\(\) => onConfigure\(item\.name\)\}/);
  assert.match(app, /const \[providerConfigs, setProviderConfigs\]/);
  assert.match(app, /configuringProvider &&/);
  assert.match(app, /Windows 凭据管理器/);
  assert.match(app, /provider-config-indicator/);
  assert.doesNotMatch(app, /provider-config-status/);
  assert.doesNotMatch(app, /已配置 · 仅本次会话/);
  assert.match(desktop, /loadDesktopProviderConfigs/);
  assert.match(desktop, /saveDesktopProviderConfig/);
  assert.match(styles, /\.provider-dialog-backdrop\s*\{/);
  assert.match(styles, /\.provider-dialog\s*\{/);
  assert.match(styles, /input\[type="password"\]::\-ms-reveal/);
  assert.match(styles, /\.provider-config-indicator\.configured\s*\{[^}]*animation:/s);
  assert.match(styles, /@keyframes provider-breathe/);
  assert.doesNotMatch(app, /localStorage\.setItem\([^\n]*(provider|api.?key|model|base.?url)/i);
});

test("collapsed text bars omit empty-state filler copy and center their action", () => {
  assert.doesNotMatch(app, /可直接粘贴文本/);
  assert.doesNotMatch(app, /暂无译文/);
  assert.match(styles, /\.text-bar-action\s*\{[^}]*height:\s*24px/s);
});

test("running jobs use honest indeterminate progress instead of fake stages", () => {
  assert.doesNotMatch(app, /const steps =/);
  assert.doesNotMatch(app, /step-list/);
  assert.match(app, /progress-orbit/);
  assert.match(app, /formatElapsed/);
  assert.match(styles, /\.progress-orbit\s*\{[^}]*animation:\s*spin/s);
});

test("PDF.js renders a selectable text layer over the canvas", () => {
  assert.match(viewer, /new pdfjs\.TextLayer/);
  assert.match(viewer, /pageProxy\.streamTextContent/);
  assert.match(viewer, /className="textLayer pdf-text-layer"/);
  assert.match(styles, /\.pdf-text-layer\s*\{[^}]*user-select:\s*text/s);
});

test("PDF rendering is interaction-stable and commits resized pages without blank frames", () => {
  assert.match(viewer, /const onPageChangeRef = useRef\(onPageChange\)/);
  assert.match(viewer, /const resizeCommitTimer = useRef/);
  assert.match(viewer, /window\.setTimeout\([\s\S]*?setContainerWidth/);
  assert.match(viewer, /const stagingCanvas = window\.document\.createElement\("canvas"\)/);
  assert.match(viewer, /visibleContext\.drawImage\(stagingCanvas, 0, 0\)/);
  assert.match(viewer, /left: `\$\{\(x0 \/ page\.width\) \* 100\}%`/);
  assert.doesNotMatch(viewer, /page\.render\(\{ canvas: canvas\.current/);
  assert.doesNotMatch(viewer, /\[containerWidth, document, onPageChange, pageNumber, zoom\]/);
});

test("continuous reading uses a bounded virtual page window and stable page observation", () => {
  assert.match(viewer, /function boundedPageWindow/);
  assert.match(viewer, /boundedPageWindow\(pageNumber, pageCount, 2\)/);
  assert.match(viewer, /pdf-continuous-stack/);
  assert.match(viewer, /data-page-number=\{page\}/);
  assert.match(viewer, /new IntersectionObserver/);
  assert.match(viewer, /entry\.intersectionRatio/);
  assert.match(viewer, /programmaticTargetPage/);
  assert.match(viewer, /function PdfPageSurface/);
  assert.match(viewer, /pageProxyRef\.current\?\.cleanup\(\)/);
  assert.match(styles, /\.pdf-continuous-stack\s*\{/);
  assert.match(styles, /\.pdf-page-slot\s*\{/);
});

test("continuous page sync broadcasts only a settled most-visible page", () => {
  assert.match(viewer, /const observedPageCandidate = useRef/);
  assert.match(viewer, /const observerCommitTimer = useRef/);
  assert.match(viewer, /scheduleObservedPageCommit/);
  assert.match(viewer, /window\.setTimeout\([\s\S]*?80\)/);
  assert.match(viewer, /if \(programmaticTargetPage\.current !== null\) return/);
  assert.match(viewer, /cancelObservedPageCandidate\(\)/);
  assert.match(app, /if \(pageSync\) setOutputPdfPage/);
  assert.match(app, /if \(pageSync\) setSourcePdfPage/);
  assert.match(app, /if \(targetPage\) setOutputPdfPage/);
  assert.match(app, /if \(targetPage\) setSourcePdfPage/);
});

test("cross-page mapping locks navigation before observers run and uses stack-relative geometry", () => {
  assert.match(viewer, /pageNumberRef\.current !== pageNumber/);
  assert.match(viewer, /programmaticTargetPage\.current = pageNumber/);
  assert.match(viewer, /programmaticScrollReleaseTimer/);
  assert.match(viewer, /if \(programmaticTargetPage\.current !== null\) return/);
  assert.match(viewer, /beginProgrammaticScroll\(readingMap\.page\.number,/);
  assert.match(viewer, /surfaceBounds\.top - rootBounds\.top \+ root\.scrollTop/);
  assert.match(viewer, /surfaceBounds\.left - rootBounds\.left \+ root\.scrollLeft/);
  assert.doesNotMatch(viewer, /const surfaceTop = surface\.offsetTop/);
});

test("Ctrl-wheel previews zoom without restarting every mounted PDF render", () => {
  assert.match(viewer, /wheelZoomPreview/);
  assert.match(viewer, /wheelZoomCommitTimer/);
  assert.match(viewer, /const displayZoom = wheelZoomPreview \?\? zoom/);
  assert.match(viewer, /displayZoom=\{displayZoom\}/);
  assert.match(viewer, /const \[renderedZoom, setRenderedZoom\]/);
  assert.match(viewer, /displayZoom \/ renderedZoom/);
  assert.doesNotMatch(viewer, /\}, \{ root, threshold:[^\n]+\}\);[\s\S]*?\}, \[containerWidth, document, pageCount, zoom\]\);/);
  assert.doesNotMatch(viewer, /scrollIntoView[\s\S]{0,300}\[containerWidth, document, pageCount, pageNumber, zoom\]/);
});

test("completed jobs consume stable per-page paragraph geometry", () => {
  assert.match(api, /reading-map\/\$\{pageNumber\}/);
  assert.match(api, /loadReadingMap\([\s\S]*?signal\?: AbortSignal/);
  assert.match(api, /loadLibraryReadingMap\([\s\S]*?signal\?: AbortSignal/);
  assert.match(app, /const \[readingMaps, setReadingMaps\]/);
  assert.match(app, /const readingMapCache = useRef/);
  assert.match(app, /const readingMapAbort = useRef/);
  assert.match(app, /new AbortController\(\)/);
  assert.match(app, /boundedReadingMapPages\(sourcePdfPage, sourcePdfPageCount, 2\)/);
  assert.match(app, /boundedReadingMapPages\(outputPdfPage, outputPdfPageCount, 2\)/);
  assert.match(app, /loadReadingMap\(liveJobId as string, page, controller\.signal\)/);
  assert.match(app, /loadLibraryReadingMap\(restoredTaskId, page, controller\.signal\)/);
  assert.match(viewer, /readingMaps\?: Record<number, PageReadingMap>/);
  assert.match(viewer, /const readingMap = readingMaps\[pageNumber\] \?\? null/);
  assert.match(viewer, /const pageMap = readingMaps\[context\.pageNumber\]/);
  assert.match(viewer, /const pageMap = readingMaps\[page\] \?\? null/);
  assert.match(viewer, /data-flow-id=\{paragraph\.id\}/);
  assert.match(viewer, /mappingSide === "source" \? paragraph\.sourceBoxes : paragraph\.translationBoxes/);
});

test("paragraph double-clicks drive linked highlights without a bulky paired-content dock", () => {
  assert.match(viewer, /selectParagraphAtPointer/);
  assert.match(viewer, /onDoubleClick=\{selectParagraphAtPointer\}/);
  assert.match(viewer, /const selectionGesture = useRef/);
  assert.match(viewer, /gesture\?\.pointerId === event\.pointerId && gesture\.moved/);
  assert.match(viewer, /gesture\.moved\) \{\s*captureTextSelectionAtPointer\(event, context\);/);
  assert.match(viewer, /onFlowSelect\?\.\(paragraph\.id, targetPage\)/);
  assert.match(viewer, /pdf-paragraph-hitbox active/);
  assert.doesNotMatch(viewer, /pdf-linked-content/);
  assert.doesNotMatch(viewer, /对应原文|对应译文/);
  assert.match(app, /const \[activeFlowId, setActiveFlowId\]/);
  assert.match(styles, /\.pdf-paragraph-hitbox\.active\s*\{[^}]*background:/s);
});

test("linked selection scrolls only the opposite reader into view", () => {
  assert.match(viewer, /selectionOrigin === mappingSide/);
  assert.match(viewer, /if \(visible\) return/);
  assert.match(viewer, /root\.scrollTo\(\{/);
  assert.match(viewer, /prefers-reduced-motion: reduce/);
  assert.match(app, /setActiveFlowOrigin\("source"\)/);
  assert.match(app, /setActiveFlowOrigin\("translation"\)/);
});

test("word selection is captured locally without inventing word alignment", () => {
  assert.match(viewer, /selectedTextWithinParagraph/);
  assert.match(viewer, /textLayer\.contains\(selection\.anchorNode\)/);
  assert.match(viewer, /const allInsideParagraph = rectangles\.every/);
  assert.match(viewer, /slice\(0, 300\)/);
  assert.match(viewer, /onTextSelect\?\.\(paragraph\.id, selectedText\.text\)/);
  assert.match(viewer, /setSelectionAnchor\(selectedText\.anchor\)/);
  assert.match(viewer, /if \(!hasNativeTextSelection\(nativeSelection, context\.textLayer\)\) \{[\s\S]*?return;/);
  assert.match(app, /setPdfTextSelection\(\{ flowId, side: "source", text: selectedText \}\)/);
  assert.doesNotMatch(viewer, /已选：/);
  assert.doesNotMatch(viewer, /translateText|loadReadingMap/);
});

test("selected text translation is explicit, transient, and uses its dedicated endpoint", () => {
  assert.match(api, /\/api\/selection-translations/);
  assert.match(viewer, /翻译所选/);
  assert.match(viewer, /onTranslateSelection/);
  assert.match(viewer, /pdf-selection-anchor/);
  assert.match(viewer, /pdf-selection-popover/);
  assert.match(app, /translateSelection\(\{/);
  assert.match(app, /selectionTranslationAbort/);
  assert.match(types, /SelectionTranslationResult = Omit<TextTranslationResult, "task">/);
  assert.doesNotMatch(viewer, /useEffect\([^)]*onTranslateSelection/s);
  assert.match(styles, /\.pdf-selection-anchor\s*\{[^}]*position:\s*absolute/s);
  assert.doesNotMatch(styles, /\.pdf-viewer-toolbar \.pdf-selection-action/);
});

test("page and zoom synchronization are independent user preferences", () => {
  assert.match(app, /useStoredBoolean\("papertrans-page-sync", true\)/);
  assert.match(app, /useStoredBoolean\("papertrans-zoom-sync", true\)/);
  assert.match(app, /if \(pageSync\) setOutputPdfPage/);
  assert.match(app, /if \(zoomSync\) setOutputPdfZoom/);
  assert.match(app, /if \(targetPage\) setOutputPdfPage/);
  assert.match(app, />同步翻页</);
  assert.match(app, />同步缩放</);
});

test("holding Space pans either PDF viewport", () => {
  assert.match(viewer, /event\.code === "Space"/);
  assert.match(viewer, /root\.scrollLeft = current\.scrollLeft - deltaX/);
  assert.match(viewer, /root\.scrollTop = current\.scrollTop - deltaY/);
  assert.match(styles, /\.pdf-canvas-viewport\.space-pan/);
  assert.match(styles, /cursor:\s*grabbing/);
});

test("library separates PDF and text work and restores completed PDFs", () => {
  assert.match(app, /className="library-columns"/);
  assert.match(app, /"PDF 翻译" : "文本翻译"/);
  assert.match(app, /restoreLibraryPdfTask/);
  assert.match(app, /libraryArtifactUrl\(restoredTask\.id, "output"\)/);
  assert.match(styles, /\.library-columns\s*\{[^}]*grid-template-columns:\s*repeat\(2/s);
});

test("library shows paper titles and bounded text previews with ellipsis", () => {
  assert.match(app, /task\.kind === "text" \? task\.preview \|\| task\.title : task\.title/);
  assert.match(app, /className="library-task-title" title=\{displayTitle\}/);
  assert.match(types, /preview\?: string/);
  assert.match(styles, /\.library-task-title\s*\{[^}]*text-overflow:\s*ellipsis[^}]*white-space:\s*nowrap/s);
});

test("task deletion and bounded storage cleanup require explicit confirmation", () => {
  assert.match(api, /deleteLibraryTask/);
  assert.match(api, /loadStorageInfo/);
  assert.match(api, /clearTranslationCache/);
  assert.match(api, /clearTemporaryUploads/);
  assert.match(api, /releaseSource/);
  assert.match(app, /function ConfirmationDialog/);
  assert.match(app, /pendingConfirmation/);
  assert.match(app, /library-delete-action/);
  assert.match(app, /原始论文和已经生成的译文文件都会保留/);
  assert.match(app, /不会删除原始论文、仓库任务或已经生成的译文文件/);
  assert.match(styles, /\.library-actions\s*\{/);
  assert.match(styles, /\.confirmation-dialog\s*\{/);
});

test("library columns are equal-height independent scroll regions with hidden scrollbars", () => {
  assert.match(app, /content-page library-page view-stage/);
  assert.match(styles, /\.library-page\s*\{[^}]*overflow:\s*hidden/s);
  assert.match(styles, /\.library-columns\s*\{[^}]*height:\s*100%/s);
  assert.match(styles, /\.library-group\s*\{[^}]*height:\s*100%/s);
  assert.match(styles, /\.library-list\s*\{[^}]*overflow-y:\s*auto/s);
  assert.match(styles, /\.library-list\s*\{[^}]*scrollbar-width:\s*none/s);
  assert.match(styles, /\.library-list::-webkit-scrollbar\s*\{[^}]*display:\s*none/s);
});

test("empty library preserves separate PDF and text task surfaces", () => {
  assert.doesNotMatch(app, /tasks\.length === 0 \?/);
  assert.match(app, /className="library-columns"/);
  assert.match(app, /暂无\{kind === "pdf" \? " PDF " : "文本"\}任务/);
});

test("application behavior rows omit redundant explanatory copy", () => {
  assert.doesNotMatch(app, /点击关闭后将彻底退出/);
  assert.doesNotMatch(app, /关闭后仍驻留系统托盘/);
  assert.doesNotMatch(app, /已使用低亮度阅读界面/);
  assert.doesNotMatch(app, /使用明亮学术配色/);
});

test("compact titlebar keeps window controls visible without a separator", () => {
  assert.match(styles, /body\s*\{[^}]*min-width:\s*0/s);
  assert.match(styles, /\.window-controls\s*\{[^}]*flex:\s*0 0 auto/s);
  assert.doesNotMatch(styles, /\.window-controls\s*\{[^}]*border-left:/s);
});

test("settings page scrolls without a visible right scrollbar", () => {
  assert.match(styles, /\.settings-page\s*\{[^}]*scrollbar-width:\s*none/s);
  assert.match(styles, /\.settings-page::-webkit-scrollbar\s*\{[^}]*display:\s*none/s);
});

test("desktop close behavior is user controlled and defaults to the tray", () => {
  assert.match(desktop, /setDesktopExitOnClose/);
  assert.match(app, /useStoredBoolean\("papertrans-exit-on-close", false\)/);
  assert.match(app, /setDesktopExitOnClose\(exitOnClose\)/);
  assert.match(app, />关闭主窗口时退出应用</);
  assert.match(app, /aria-checked=\{exitOnClose\}/);
});

test("output directory and dark theme are durable non-sensitive desktop preferences", () => {
  assert.match(app, /useStoredString\("papertrans-output-directory"/);
  assert.match(app, /默认输出目录/);
  assert.match(app, /选择文件夹/);
  assert.match(app, /不会移动已有任务/);
  assert.match(app, /useStoredString\("papertrans-theme", "light"\)/);
  assert.match(app, /暗色主题/);
  assert.match(app, /document\.documentElement\.dataset\.theme = theme/);
  assert.match(desktop, /setDesktopTheme/);
  assert.match(styles, /:root\[data-theme="dark"\]/);
});

test("switches and buttons share compositor-friendly motion feedback", () => {
  assert.match(styles, /button\s*\{[^}]*transition:[^}]*scale[^}]*translate/s);
  assert.match(styles, /button:not\(:disabled\):active\s*\{[^}]*scale:\s*\.97[^}]*translate:\s*0 1px/s);
  assert.match(styles, /\.switch span\s*\{[^}]*transform:\s*translateX\(0\)[^}]*transition:[^}]*transform/s);
  assert.match(styles, /\.switch\.on span\s*\{[^}]*transform:\s*translateX\(20px\)/s);
  assert.doesNotMatch(styles, /\.switch\.on\s*\{[^}]*justify-content:\s*flex-end/s);
  assert.match(styles, /@media \(prefers-reduced-motion: reduce\)[\s\S]*button[\s\S]*transition-duration:\s*1ms !important/);
});

test("collapsed settings no longer advertises mock or OCR status", () => {
  assert.match(app, /collapsed-settings-summary" aria-hidden="true"/);
  assert.doesNotMatch(app, /Mock 版本测试 · OCR 就绪/);
});

test("target language is a real selector across major world languages", () => {
  // The dummy static control is gone; the label now drives a live dropdown.
  assert.doesNotMatch(app, /className="static-select" aria-label="目标语言"/);
  assert.match(app, /options=\{TARGET_LANGUAGES\}[\s\S]*?ariaLabel="目标语言"/);
  for (const label of ["简体中文", "English", "日本語", "한국어", "Français", "Español", "Deutsch", "Русский"]) {
    assert.ok(app.includes(label), `TARGET_LANGUAGES missing ${label}`);
  }
});

test("selected target language flows into PDF and text translation requests", () => {
  assert.match(app, /useStoredString\("papertrans-target-language"/);
  // PDF job payload and both text endpoints send the chosen language.
  const targetLanguageSends = app.match(/\n\s*targetLanguage,\n/g) ?? [];
  assert.ok(targetLanguageSends.length >= 3, "targetLanguage must reach all three requests");
  assert.doesNotMatch(app, /targetLanguage:\s*"zh-CN"/);
});

test("dropdown popup is a fixed-size scrollable menu that consistent-flips", () => {
  // Fixed cap + scroll so long option lists never force an oversized popup.
  assert.match(styles, /\.rounded-select-menu\s*\{[^}]*max-height:\s*208px/s);
  assert.match(styles, /\.rounded-select-menu\s*\{[^}]*overflow-y:\s*auto/s);
  // Menu text matches the trigger (12px) instead of inheriting the body size.
  assert.match(styles, /\.rounded-select-menu\s*\{[^}]*font-size:\s*12px/s);
  // Up/down decision uses a fixed height so every select flips the same way.
  assert.match(app, /spaceBelow\s*<\s*MENU_MAX_HEIGHT\s*\+\s*MENU_GAP/);
});

test("scrolling inside the dropdown browses options instead of closing it", () => {
  assert.match(app, /menu\.current\?\.contains\(event\.target as Node\)\)\s*return/);
});

test("resize handles use softly rounded indicators like other components", () => {
  assert.match(styles, /\.resize-handle span\s*\{[^}]*border-radius:\s*2px/s);
});

test("field labels do not extend the clickable area of their control", () => {
  // Fields are wrapped in <div className="field">, never <label>, so clicking the
  // text label (or the gap around it) no longer opens a dropdown or focuses an input.
  assert.doesNotMatch(app, /<label[\s>]/);
  assert.match(styles, /label,\s*\.field\s*\{/);
  assert.match(app, /className="field">\s*<span>目标语言/);
  // Native inputs that lost their <label> association keep an accessible name.
  assert.match(app, /placeholder="输入密钥"[^>]*aria-label="API Key"/);
});

test("model field auto-detects available models and lets you pick one", () => {
  assert.match(app, /function ModelCombobox\(/);
  assert.match(app, /listProviderModels\(\{ provider, apiKey, baseUrl/);
  assert.match(app, /modelDetectDisabledReason\(/);
  assert.match(api, /\/api\/provider-models/);
  assert.match(api, /export async function listProviderModels/);
  // The old non-functional "高级设置" affordance is replaced by real detection.
  assert.doesNotMatch(app, /className="text-button">高级设置/);
});

test("library page is full-bleed like the translate workspace", () => {
  // Tight uniform padding (matches .translate-page) instead of the inset content-page frame,
  // and no reserved scrollbar gutter so the two columns reach the edges symmetrically.
  assert.match(styles, /\.library-page\s*\{[^}]*padding:\s*10px/s);
  assert.match(styles, /\.library-page\s*\{[^}]*scrollbar-gutter:\s*auto/s);
});
