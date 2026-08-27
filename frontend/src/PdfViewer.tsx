import { useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties, MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent, ReactNode } from "react";
import type { PDFDocumentLoadingTask, PDFDocumentProxy, PDFPageProxy, RenderTask, TextLayer } from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import type { PageReadingMap, PdfBox, PdfTextSelection, ReadingParagraph, SelectionTranslationResult } from "./types";

type PdfViewerProps = {
  url: string;
  pageNumber: number;
  zoom: number;
  label: string;
  onPageChange: (page: number) => void;
  onPageCount: (count: number) => void;
  onZoomChange: (zoom: number) => void;
  readingMaps?: Record<number, PageReadingMap>;
  mappingSide?: "source" | "translation";
  activeFlowId?: string | null;
  selectionOrigin?: "source" | "translation" | null;
  textSelection?: PdfTextSelection | null;
  selectionTranslation?: SelectionTranslationResult | null;
  selectionTranslationBusy?: boolean;
  selectionTranslationError?: string;
  onTranslateSelection?: () => void;
  onDismissSelectionTranslation?: () => void;
  onTextSelect?: (flowId: string, selectedText: string) => void;
  onFlowSelect?: (flowId: string, targetPage?: number) => void;
  onFlowClear?: () => void;
};

type SelectionAnchor = {
  actionLeft: number;
  actionTop: number;
  popoverLeft: number;
  popoverTop: number;
};

type PagePointerContext = {
  pageNumber: number;
  surface: HTMLDivElement;
  textLayer: HTMLDivElement;
};

function ViewerIcon({ name }: { name: string }) {
  return <span className="material-symbols-outlined" aria-hidden="true">{name}</span>;
}

export function PdfViewer({
  url,
  pageNumber,
  zoom,
  label,
  onPageChange,
  onPageCount,
  onZoomChange,
  readingMaps = {},
  mappingSide = "source",
  activeFlowId = null,
  selectionOrigin = null,
  textSelection = null,
  selectionTranslation = null,
  selectionTranslationBusy = false,
  selectionTranslationError = "",
  onTranslateSelection,
  onDismissSelectionTranslation,
  onTextSelect,
  onFlowSelect,
  onFlowClear,
}: PdfViewerProps) {
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null);
  const [pageCount, setPageCount] = useState(0);
  const [containerWidth, setContainerWidth] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [spacePressed, setSpacePressed] = useState(false);
  const [panning, setPanning] = useState(false);
  const [selectionAnchor, setSelectionAnchor] = useState<SelectionAnchor | null>(null);
  const [defaultPageRatio, setDefaultPageRatio] = useState(1.414);
  const [pageRatios, setPageRatios] = useState<Record<number, number>>({});
  const [wheelZoomPreview, setWheelZoomPreview] = useState<number | null>(null);
  const viewportRoot = useRef<HTMLDivElement>(null);
  const surfaceNodes = useRef(new Map<number, HTMLDivElement>());
  const visibilityRatios = useRef(new Map<number, number>());
  const pageNumberRef = useRef(pageNumber);
  const observerPage = useRef<number | null>(null);
  const observedPageCandidate = useRef<number | null>(null);
  const observerCommitTimer = useRef<number | null>(null);
  const programmaticTargetPage = useRef<number | null>(null);
  const programmaticScrollReleaseTimer = useRef<number | null>(null);
  const onPageChangeRef = useRef(onPageChange);
  const onPageCountRef = useRef(onPageCount);
  const onZoomChangeRef = useRef(onZoomChange);
  const resizeCommitTimer = useRef<number | null>(null);
  const committedZoomRef = useRef(zoom);
  const wheelZoomPreviewRef = useRef<number | null>(null);
  const wheelZoomCommitTimer = useRef<number | null>(null);
  const pan = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    scrollLeft: number;
    scrollTop: number;
    moved: boolean;
  } | null>(null);
  const selectionGesture = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    moved: boolean;
  } | null>(null);
  onPageChangeRef.current = onPageChange;
  onPageCountRef.current = onPageCount;
  onZoomChangeRef.current = onZoomChange;
  committedZoomRef.current = zoom;
  if (pageNumberRef.current !== pageNumber) {
    if (observerPage.current !== pageNumber) programmaticTargetPage.current = pageNumber;
    pageNumberRef.current = pageNumber;
  }

  const displayZoom = wheelZoomPreview ?? zoom;
  const readingMap = readingMaps[pageNumber] ?? null;

  const registerSurface = useCallback((page: number, node: HTMLDivElement | null) => {
    if (node) surfaceNodes.current.set(page, node);
    else surfaceNodes.current.delete(page);
  }, []);

  const recordPageRatio = useCallback((page: number, ratio: number) => {
    setPageRatios((current) => Math.abs((current[page] ?? 0) - ratio) < 0.0001
      ? current
      : { ...current, [page]: ratio });
  }, []);

  const cancelObservedPageCandidate = useCallback(() => {
    observedPageCandidate.current = null;
    if (observerCommitTimer.current !== null) window.clearTimeout(observerCommitTimer.current);
    observerCommitTimer.current = null;
  }, []);

  const mostVisibleObservedPage = useCallback((): number | null => {
    let page: number | null = null;
    let largestRatio = 0;
    for (const [candidate, ratio] of visibilityRatios.current) {
      if (ratio > largestRatio) {
        page = candidate;
        largestRatio = ratio;
      }
    }
    return largestRatio > 0 ? page : null;
  }, []);

  const scheduleObservedPageCommit = useCallback((page: number) => {
    if (page === pageNumberRef.current) {
      cancelObservedPageCandidate();
      return;
    }
    if (observedPageCandidate.current === page && observerCommitTimer.current !== null) return;
    cancelObservedPageCandidate();
    observedPageCandidate.current = page;
    observerCommitTimer.current = window.setTimeout(() => {
      observerCommitTimer.current = null;
      const candidate = observedPageCandidate.current;
      observedPageCandidate.current = null;
      if (programmaticTargetPage.current !== null || candidate !== page) return;
      if (mostVisibleObservedPage() !== page || page === pageNumberRef.current) return;
      observerPage.current = page;
      onPageChangeRef.current(page);
    }, 80);
  }, [cancelObservedPageCandidate, mostVisibleObservedPage]);

  const beginProgrammaticScroll = useCallback((page: number, duration: number) => {
    cancelObservedPageCandidate();
    programmaticTargetPage.current = page;
    if (programmaticScrollReleaseTimer.current !== null) {
      window.clearTimeout(programmaticScrollReleaseTimer.current);
    }
    programmaticScrollReleaseTimer.current = window.setTimeout(() => {
      programmaticScrollReleaseTimer.current = null;
      if (programmaticTargetPage.current === page) programmaticTargetPage.current = null;
    }, duration);
  }, [cancelObservedPageCandidate]);

  useEffect(() => () => {
    cancelObservedPageCandidate();
    if (programmaticScrollReleaseTimer.current !== null) {
      window.clearTimeout(programmaticScrollReleaseTimer.current);
    }
  }, [cancelObservedPageCandidate]);

  useEffect(() => {
    if (textSelection?.side !== mappingSide) setSelectionAnchor(null);
  }, [mappingSide, textSelection]);

  useEffect(() => {
    const editable = (target: EventTarget | null) => (
      target instanceof HTMLElement
      && (target.matches("input, textarea, select, [contenteditable='true']") || target.isContentEditable)
    );
    const keyDown = (event: globalThis.KeyboardEvent) => {
      if (event.code === "Space" && !editable(event.target)) {
        event.preventDefault();
        setSpacePressed(true);
      }
      if (event.key === "Escape") {
        window.getSelection()?.removeAllRanges();
        onFlowClear?.();
      }
    };
    const keyUp = (event: globalThis.KeyboardEvent) => {
      if (event.code === "Space") setSpacePressed(false);
    };
    const blur = () => {
      setSpacePressed(false);
      setPanning(false);
      pan.current = null;
      selectionGesture.current = null;
    };
    window.addEventListener("keydown", keyDown);
    window.addEventListener("keyup", keyUp);
    window.addEventListener("blur", blur);
    return () => {
      window.removeEventListener("keydown", keyDown);
      window.removeEventListener("keyup", keyUp);
      window.removeEventListener("blur", blur);
    };
  }, [onFlowClear]);

  useEffect(() => {
    if (!activeFlowId || !readingMap || selectionOrigin === mappingSide) return;
    const root = viewportRoot.current;
    const surface = surfaceNodes.current.get(readingMap.page.number)
      ?? root?.querySelector<HTMLDivElement>(`.pdf-page-slot[data-page-number="${readingMap.page.number}"] .pdf-page-surface`);
    const paragraph = readingMap.paragraphs.find((item) => item.id === activeFlowId);
    if (!root || !surface || !paragraph) return;
    const boxes = mappingSide === "source" ? paragraph.sourceBoxes : paragraph.translationBoxes;
    if (boxes.length === 0 || readingMap.page.width <= 0) return;

    const frame = window.requestAnimationFrame(() => {
      const rootBounds = root.getBoundingClientRect();
      const surfaceBounds = surface.getBoundingClientRect();
      const scale = surfaceBounds.width / readingMap.page.width;
      const x0 = Math.min(...boxes.map((box) => box[0])) * scale;
      const y0 = Math.min(...boxes.map((box) => box[1])) * scale;
      const x1 = Math.max(...boxes.map((box) => box[2])) * scale;
      const y1 = Math.max(...boxes.map((box) => box[3])) * scale;
      const surfaceLeft = surfaceBounds.left - rootBounds.left + root.scrollLeft;
      const surfaceTop = surfaceBounds.top - rootBounds.top + root.scrollTop;
      const visible = (
        surfaceLeft + x0 >= root.scrollLeft
        && surfaceLeft + x1 <= root.scrollLeft + root.clientWidth
        && surfaceTop + y0 >= root.scrollTop
        && surfaceTop + y1 <= root.scrollTop + root.clientHeight
      );
      if (visible) return;
      const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      beginProgrammaticScroll(readingMap.page.number, reducedMotion ? 32 : 720);
      root.scrollTo({
        left: Math.max(0, surfaceLeft + (x0 + x1) / 2 - root.clientWidth / 2),
        top: Math.max(0, surfaceTop + (y0 + y1) / 2 - root.clientHeight / 2),
        behavior: reducedMotion ? "auto" : "smooth",
      });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [activeFlowId, beginProgrammaticScroll, mappingSide, readingMap, selectionOrigin]);

  useEffect(() => {
    const root = viewportRoot.current;
    if (!root) return;
    let initialized = false;
    const commitWidth = (width: number) => {
      setContainerWidth((current) => Math.abs(current - width) < 1 ? current : width);
    };
    const observer = new ResizeObserver(([entry]) => {
      const width = Math.round(entry.contentRect.width);
      if (!initialized) {
        initialized = true;
        commitWidth(width);
        return;
      }
      if (resizeCommitTimer.current !== null) window.clearTimeout(resizeCommitTimer.current);
      resizeCommitTimer.current = window.setTimeout(() => {
        resizeCommitTimer.current = null;
        setContainerWidth((current) => Math.abs(current - width) < 1 ? current : width);
      }, 120);
    });
    observer.observe(root);
    return () => {
      observer.disconnect();
      if (resizeCommitTimer.current !== null) window.clearTimeout(resizeCommitTimer.current);
      resizeCommitTimer.current = null;
    };
  }, []);

  useEffect(() => {
    const root = viewportRoot.current;
    if (!root) return;
    const handleWheel = (event: WheelEvent) => {
      if (!event.ctrlKey) return;
      event.preventDefault();
      const currentZoom = wheelZoomPreviewRef.current ?? committedZoomRef.current;
      const delta = event.deltaY < 0 ? 0.1 : -0.1;
      const nextZoom = Math.min(1.75, Math.max(0.75, Number((currentZoom + delta).toFixed(2))));
      if (nextZoom === currentZoom) return;
      const bounds = root.getBoundingClientRect();
      const pointerX = event.clientX - bounds.left;
      const pointerY = event.clientY - bounds.top;
      const contentX = root.scrollLeft + pointerX;
      const contentY = root.scrollTop + pointerY;
      wheelZoomPreviewRef.current = nextZoom;
      setWheelZoomPreview(nextZoom);
      window.requestAnimationFrame(() => {
        const ratio = nextZoom / currentZoom;
        root.scrollLeft = Math.max(0, contentX * ratio - pointerX);
        root.scrollTop = Math.max(0, contentY * ratio - pointerY);
      });
      if (wheelZoomCommitTimer.current !== null) window.clearTimeout(wheelZoomCommitTimer.current);
      wheelZoomCommitTimer.current = window.setTimeout(() => {
        wheelZoomCommitTimer.current = null;
        const target = wheelZoomPreviewRef.current;
        if (target !== null) onZoomChangeRef.current(target);
      }, 140);
    };
    root.addEventListener("wheel", handleWheel, { passive: false });
    return () => {
      root.removeEventListener("wheel", handleWheel);
      if (wheelZoomCommitTimer.current !== null) window.clearTimeout(wheelZoomCommitTimer.current);
      wheelZoomCommitTimer.current = null;
    };
  }, []);

  useEffect(() => {
    const target = wheelZoomPreviewRef.current;
    if (target === null || Math.abs(target - zoom) >= 0.001) return;
    wheelZoomPreviewRef.current = null;
    setWheelZoomPreview(null);
  }, [zoom]);

  useEffect(() => {
    let active = true;
    let loadingTask: PDFDocumentLoadingTask | null = null;
    setDocument(null);
    setPageCount(0);
    setPageRatios({});
    setLoading(true);
    setError("");
    void import("pdfjs-dist").then((pdfjs) => {
      if (!active) return;
      pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;
      loadingTask = pdfjs.getDocument({ url });
      return loadingTask.promise;
    }).then(async (loaded) => {
      if (!active || !loaded) return;
      const firstPage = await loaded.getPage(1);
      if (!active) return;
      const firstViewport = firstPage.getViewport({ scale: 1 });
      setDefaultPageRatio(firstViewport.height / firstViewport.width);
      setDocument(loaded);
      setPageCount(loaded.numPages);
      onPageCountRef.current(loaded.numPages);
      setLoading(false);
    }).catch(() => {
      if (active) {
        setLoading(false);
        setError("PDF 无法载入");
      }
    });
    return () => {
      active = false;
      void loadingTask?.destroy();
    };
  }, [url]);

  useEffect(() => {
    const root = viewportRoot.current;
    if (!root || !document || pageCount <= 0) return;
    visibilityRatios.current.clear();
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        const page = Number((entry.target as HTMLElement).dataset.pageNumber);
        if (Number.isInteger(page)) visibilityRatios.current.set(page, entry.intersectionRatio);
      }
      const mostVisiblePage = mostVisibleObservedPage();
      if (!mostVisiblePage) return;
      if (programmaticTargetPage.current !== null) return;
      scheduleObservedPageCommit(mostVisiblePage);
    }, { root, threshold: [0, 0.1, 0.25, 0.5, 0.75, 1] });
    root.querySelectorAll<HTMLElement>(".pdf-page-slot").forEach((slot) => observer.observe(slot));
    return () => {
      observer.disconnect();
      cancelObservedPageCandidate();
    };
  }, [cancelObservedPageCandidate, document, mostVisibleObservedPage, pageCount, scheduleObservedPageCommit]);

  useEffect(() => {
    if (!document || pageCount <= 0) return;
    if (observerPage.current === pageNumber) {
      observerPage.current = null;
      return;
    }
    const root = viewportRoot.current;
    const target = root?.querySelector<HTMLElement>(`.pdf-page-slot[data-page-number="${pageNumber}"]`);
    if (!target) return;
    programmaticTargetPage.current = pageNumber;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    beginProgrammaticScroll(pageNumber, reducedMotion ? 32 : 720);
    target.scrollIntoView({ block: "start", inline: "center", behavior: reducedMotion ? "auto" : "smooth" });
  }, [beginProgrammaticScroll, document, pageCount, pageNumber]);

  const changeZoom = (delta: number) => {
    if (wheelZoomCommitTimer.current !== null) window.clearTimeout(wheelZoomCommitTimer.current);
    wheelZoomCommitTimer.current = null;
    wheelZoomPreviewRef.current = null;
    setWheelZoomPreview(null);
    onZoomChangeRef.current(Math.min(1.75, Math.max(0.75, Number((displayZoom + delta).toFixed(2)))));
  };

  const captureTextSelectionAtPointer = (
    event: ReactPointerEvent<HTMLDivElement>,
    context: PagePointerContext,
  ) => {
    const pageMap = readingMaps[context.pageNumber];
    if (event.button !== 0 || !pageMap) return;
    const bounds = context.surface.getBoundingClientRect();
    if (bounds.width <= 0 || bounds.height <= 0) return;
    const tolerance = 3 / Math.max(0.1, bounds.width / pageMap.page.width);
    const nativeSelection = window.getSelection();
    if (!hasNativeTextSelection(nativeSelection, context.textLayer)) {
      if (textSelection?.side === mappingSide) {
        setSelectionAnchor(null);
        onFlowClear?.();
      }
      return;
    }
    const paragraph = paragraphAtClientPoint(
      pageMap,
      mappingSide,
      event.clientX,
      event.clientY,
      bounds,
      tolerance,
    );
    if (paragraph) {
      const selectedText = selectedTextWithinParagraph(
        nativeSelection,
        context.textLayer,
        pageMap,
        mappingSide,
        paragraph,
        bounds,
        tolerance,
      );
      onFlowClear?.();
      if (selectedText) {
        setSelectionAnchor(selectedText.anchor);
        onTextSelect?.(paragraph.id, selectedText.text);
      } else {
        setSelectionAnchor(null);
      }
    } else {
      setSelectionAnchor(null);
      onFlowClear?.();
    }
  };

  const selectParagraphAtPointer = (
    event: ReactMouseEvent<HTMLDivElement>,
    context: PagePointerContext,
  ) => {
    const pageMap = readingMaps[context.pageNumber];
    if (event.button !== 0 || !pageMap || spacePressed) return;
    event.preventDefault();
    window.getSelection()?.removeAllRanges();
    setSelectionAnchor(null);
    const bounds = context.surface.getBoundingClientRect();
    if (bounds.width <= 0 || bounds.height <= 0) return;
    const tolerance = 3 / Math.max(0.1, bounds.width / pageMap.page.width);
    const paragraph = paragraphAtClientPoint(
      pageMap,
      mappingSide,
      event.clientX,
      event.clientY,
      bounds,
      tolerance,
    );
    if (paragraph) {
      const targetPages = mappingSide === "source"
        ? paragraph.translationPageNumbers
        : paragraph.sourcePageNumbers;
      const targetPage = targetPages.includes(pageMap.page.number)
        ? pageMap.page.number
        : targetPages[0];
      onFlowSelect?.(paragraph.id, targetPage);
    }
    else onFlowClear?.();
  };

  const startPan = (event: ReactPointerEvent<HTMLDivElement>) => {
    const root = viewportRoot.current;
    if (event.button !== 0 || !root) return;
    if (!spacePressed) {
      selectionGesture.current = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        moved: false,
      };
      return;
    }
    selectionGesture.current = null;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    pan.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      scrollLeft: root.scrollLeft,
      scrollTop: root.scrollTop,
      moved: false,
    };
    setPanning(true);
  };

  const movePan = (event: ReactPointerEvent<HTMLDivElement>) => {
    const gesture = selectionGesture.current;
    if (gesture?.pointerId === event.pointerId && (
      Math.abs(event.clientX - gesture.startX) > 2
      || Math.abs(event.clientY - gesture.startY) > 2
    )) gesture.moved = true;
    const current = pan.current;
    const root = viewportRoot.current;
    if (!current || current.pointerId !== event.pointerId || !root) return;
    const deltaX = event.clientX - current.startX;
    const deltaY = event.clientY - current.startY;
    if (Math.abs(deltaX) > 2 || Math.abs(deltaY) > 2) current.moved = true;
    root.scrollLeft = current.scrollLeft - deltaX;
    root.scrollTop = current.scrollTop - deltaY;
  };

  const finishPointer = (event: ReactPointerEvent<HTMLDivElement>, context: PagePointerContext) => {
    const current = pan.current;
    if (current?.pointerId === event.pointerId) {
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
      pan.current = null;
      selectionGesture.current = null;
      setPanning(false);
      return;
    }
    const gesture = selectionGesture.current;
    selectionGesture.current = null;
    if (gesture?.pointerId === event.pointerId && gesture.moved) {
      captureTextSelectionAtPointer(event, context);
    } else if (textSelection?.side === mappingSide) {
      setSelectionAnchor(null);
      onFlowClear?.();
    }
  };

  const cancelPan = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (selectionGesture.current?.pointerId === event.pointerId) selectionGesture.current = null;
    const current = pan.current;
    if (current?.pointerId !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    pan.current = null;
    setPanning(false);
  };

  const canTranslateSelection = (
    mappingSide === "source"
    && textSelection?.side === "source"
    && Boolean(textSelection.text)
    && Boolean(selectionAnchor)
    && Boolean(onTranslateSelection)
  );
  const showSelectionPopover = canTranslateSelection && (
    selectionTranslationBusy
    || Boolean(selectionTranslationError)
    || Boolean(selectionTranslation)
  );
  const renderWindowPages = new Set(boundedPageWindow(pageNumber, pageCount, 2));
  const pageCssWidth = Math.max(1, (containerWidth - 24) * displayZoom);
  const pages = Array.from({ length: pageCount }, (_, index) => index + 1);

  return (
    <div className="pdf-viewer">
      <div className="pdf-viewer-toolbar">
        <span className="pdf-viewer-label">
          <span>{label}</span>
        </span>
        <div className="pdf-page-controls">
          <button aria-label="上一页" title="上一页" disabled={pageNumber <= 1} onClick={() => onPageChangeRef.current(pageNumber - 1)}><ViewerIcon name="chevron_left" /></button>
          <span>{pageCount ? `${Math.min(pageNumber, pageCount)} / ${pageCount}` : "— / —"}</span>
          <button aria-label="下一页" title="下一页" disabled={!pageCount || pageNumber >= pageCount} onClick={() => onPageChangeRef.current(pageNumber + 1)}><ViewerIcon name="chevron_right" /></button>
        </div>
        <div className="pdf-zoom-controls">
          <button aria-label="缩小" title="缩小" disabled={displayZoom <= 0.75} onClick={() => changeZoom(-0.25)}><ViewerIcon name="remove" /></button>
          <span>{Math.round(displayZoom * 100)}%</span>
          <button aria-label="放大" title="放大" disabled={displayZoom >= 1.75} onClick={() => changeZoom(0.25)}><ViewerIcon name="add" /></button>
        </div>
      </div>
      <div className={panning ? "pdf-canvas-viewport panning" : spacePressed ? "pdf-canvas-viewport space-pan" : "pdf-canvas-viewport"} ref={viewportRoot}>
        <div className="pdf-continuous-stack">
          {pages.map((page) => {
            const ratio = pageRatios[page] ?? defaultPageRatio;
            const slotStyle = { width: pageCssWidth, height: pageCssWidth * ratio };
            const pageMap = readingMaps[page] ?? null;
            return (
              <div className="pdf-page-slot" data-page-number={page} key={page} style={slotStyle}>
                {document && renderWindowPages.has(page) ? (
                  <PdfPageSurface document={document} pageNumber={page} containerWidth={containerWidth}
                    zoom={zoom} displayZoom={displayZoom} label={label} registerSurface={registerSurface} onPageRatio={recordPageRatio}
                    onPointerDown={startPan} onPointerMove={movePan} onPointerUp={finishPointer}
                    onPointerCancel={cancelPan} onDoubleClick={selectParagraphAtPointer}
                    paragraphLayer={(
                      <div className="pdf-paragraph-layer" aria-hidden="true">
                        {pageMap?.paragraphs.flatMap((paragraph) => {
                          const boxes = mappingSide === "source" ? paragraph.sourceBoxes : paragraph.translationBoxes;
                          return boxes.map((box, index) => (
                            <span className={paragraph.id === activeFlowId ? "pdf-paragraph-hitbox active" : "pdf-paragraph-hitbox"}
                              data-flow-id={paragraph.id} key={`${paragraph.id}-${index}`} style={boxStyle(box, pageMap.page)} />
                          ));
                        })}
                      </div>
                    )}
                    overlay={page === pageNumber ? (
                      <>
                        {canTranslateSelection && selectionAnchor && (
                          <div className="pdf-selection-anchor"
                            style={{ left: selectionAnchor.actionLeft, top: selectionAnchor.actionTop }}
                            onPointerDown={(event) => event.stopPropagation()}
                            onPointerUp={(event) => event.stopPropagation()}
                            onDoubleClick={(event) => event.stopPropagation()}>
                            <button className="pdf-selection-action" type="button" disabled={selectionTranslationBusy}
                              onClick={onTranslateSelection} title="翻译所选文本">
                              <ViewerIcon name="translate" />翻译所选
                            </button>
                          </div>
                        )}
                        {showSelectionPopover && selectionAnchor && (
                          <aside className={selectionTranslationError ? "pdf-selection-popover error" : "pdf-selection-popover"}
                            style={{ left: selectionAnchor.popoverLeft, top: selectionAnchor.popoverTop }} aria-live="polite"
                            onPointerDown={(event) => event.stopPropagation()}
                            onPointerUp={(event) => event.stopPropagation()}
                            onDoubleClick={(event) => event.stopPropagation()}>
                            <header>
                              <span><ViewerIcon name="translate" /><strong>所选译文</strong></span>
                              <button type="button" aria-label="关闭所选译文" title="关闭" onClick={onDismissSelectionTranslation}><ViewerIcon name="close" /></button>
                            </header>
                            {selectionTranslationBusy ? (
                              <div className="pdf-selection-progress"><span className="spinner" />正在翻译所选内容</div>
                            ) : selectionTranslationError ? (
                              <div className="pdf-selection-error"><ViewerIcon name="error" />{selectionTranslationError}</div>
                            ) : selectionTranslation ? (
                              <div className="pdf-selection-result">
                                <small title={textSelection?.text}>{textSelection?.text}</small>
                                <p>{selectionTranslation.translation}</p>
                                <span>{selectionTranslation.provider}</span>
                              </div>
                            ) : null}
                          </aside>
                        )}
                      </>
                    ) : null} />
                ) : <div className="pdf-page-placeholder" aria-hidden="true" />}
              </div>
            );
          })}
        </div>
        {loading && <div className="pdf-viewer-state"><span className="spinner pdf-viewer-spinner" />正在载入页面</div>}
        {error && <div className="pdf-viewer-state error">{error}</div>}
      </div>
    </div>
  );
}

function PdfPageSurface({
  document,
  pageNumber,
  containerWidth,
  zoom,
  displayZoom,
  label,
  registerSurface,
  onPageRatio,
  onPointerDown,
  onPointerMove,
  onPointerUp,
  onPointerCancel,
  onDoubleClick,
  paragraphLayer,
  overlay,
}: {
  document: PDFDocumentProxy;
  pageNumber: number;
  containerWidth: number;
  zoom: number;
  displayZoom: number;
  label: string;
  registerSurface: (page: number, node: HTMLDivElement | null) => void;
  onPageRatio: (page: number, ratio: number) => void;
  onPointerDown: (event: ReactPointerEvent<HTMLDivElement>) => void;
  onPointerMove: (event: ReactPointerEvent<HTMLDivElement>) => void;
  onPointerUp: (event: ReactPointerEvent<HTMLDivElement>, context: PagePointerContext) => void;
  onPointerCancel: (event: ReactPointerEvent<HTMLDivElement>) => void;
  onDoubleClick: (event: ReactMouseEvent<HTMLDivElement>, context: PagePointerContext) => void;
  paragraphLayer: ReactNode;
  overlay: ReactNode;
}) {
  const surface = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const textLayerRoot = useRef<HTMLDivElement>(null);
  const pageProxyRef = useRef<PDFPageProxy | null>(null);
  const displayZoomRef = useRef(displayZoom);
  const hasRenderedPage = useRef(false);
  const [renderedZoom, setRenderedZoom] = useState(zoom);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  displayZoomRef.current = displayZoom;

  useEffect(() => {
    registerSurface(pageNumber, surface.current);
    return () => {
      registerSurface(pageNumber, null);
      pageProxyRef.current?.cleanup();
      pageProxyRef.current = null;
    };
  }, [pageNumber, registerSurface]);

  useEffect(() => {
    if (!canvas.current || containerWidth <= 0) return;
    let active = true;
    let renderTask: RenderTask | null = null;
    let textLayer: TextLayer | null = null;
    let pageProxy: PDFPageProxy | null = null;
    if (!hasRenderedPage.current) setLoading(true);
    setError("");
    const render = async () => {
      pageProxy = await document.getPage(pageNumber);
      if (!active || !canvas.current || !surface.current || !textLayerRoot.current) return;
      pageProxyRef.current = pageProxy;
      const base = pageProxy.getViewport({ scale: 1 });
      onPageRatio(pageNumber, base.height / base.width);
      const fitScale = Math.max(0.1, (containerWidth - 24) / base.width);
      const cssScale = fitScale * zoom;
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
      const cssViewport = pageProxy.getViewport({ scale: cssScale });
      const renderViewport = pageProxy.getViewport({ scale: cssScale * pixelRatio });
      const stagingCanvas = window.document.createElement("canvas");
      stagingCanvas.width = Math.ceil(renderViewport.width);
      stagingCanvas.height = Math.ceil(renderViewport.height);
      const stagingContext = stagingCanvas.getContext("2d", { alpha: false });
      if (!stagingContext) throw new Error("Canvas is unavailable");
      const stagingTextLayer = window.document.createElement("div");
      stagingTextLayer.style.setProperty("--total-scale-factor", String(cssScale));
      renderTask = pageProxy.render({ canvas: stagingCanvas, canvasContext: stagingContext, viewport: renderViewport });
      const pdfjs = await import("pdfjs-dist");
      if (!active) return;
      textLayer = new pdfjs.TextLayer({
        textContentSource: pageProxy.streamTextContent({ includeMarkedContent: true }),
        container: stagingTextLayer,
        viewport: cssViewport,
      });
      await Promise.all([renderTask.promise, textLayer.render()]);
      if (!active || !canvas.current || !surface.current || !textLayerRoot.current) return;
      const visibleCanvas = canvas.current;
      surface.current.style.transform = `scale(${displayZoomRef.current / zoom})`;
      visibleCanvas.width = stagingCanvas.width;
      visibleCanvas.height = stagingCanvas.height;
      visibleCanvas.style.width = `${Math.ceil(cssViewport.width)}px`;
      visibleCanvas.style.height = `${Math.ceil(cssViewport.height)}px`;
      const visibleContext = visibleCanvas.getContext("2d", { alpha: false });
      if (!visibleContext) throw new Error("Canvas is unavailable");
      visibleContext.drawImage(stagingCanvas, 0, 0);
      surface.current.style.width = `${Math.ceil(cssViewport.width)}px`;
      surface.current.style.height = `${Math.ceil(cssViewport.height)}px`;
      surface.current.style.setProperty("--total-scale-factor", String(cssScale));
      textLayerRoot.current.replaceChildren(...Array.from(stagingTextLayer.childNodes));
      hasRenderedPage.current = true;
      setRenderedZoom(zoom);
      setLoading(false);
    };
    void render().catch((reason: unknown) => {
      const name = reason instanceof Error ? reason.name : "";
      if (active && name !== "RenderingCancelledException") {
        setLoading(false);
        setError("页面渲染失败");
      }
    });
    return () => {
      active = false;
      renderTask?.cancel();
      textLayer?.cancel();
    };
  }, [containerWidth, document, onPageRatio, pageNumber, zoom]);

  const pointerContext = (): PagePointerContext | null => (
    surface.current && textLayerRoot.current
      ? { pageNumber, surface: surface.current, textLayer: textLayerRoot.current }
      : null
  );

  return (
    <div className="pdf-page-surface" ref={surface}
      style={{ transform: `scale(${displayZoom / renderedZoom})`, transformOrigin: "top left" }}
      onPointerDown={onPointerDown} onPointerMove={onPointerMove}
      onPointerUp={(event) => { const context = pointerContext(); if (context) onPointerUp(event, context); }}
      onPointerCancel={onPointerCancel}
      onDoubleClick={(event) => { const context = pointerContext(); if (context) onDoubleClick(event, context); }}>
      <canvas ref={canvas} role="img" aria-label={`${label}第 ${pageNumber} 页`} />
      {paragraphLayer}
      <div className="textLayer pdf-text-layer" ref={textLayerRoot} />
      {overlay}
      {loading && <div className="pdf-page-render-state"><span className="spinner pdf-viewer-spinner" />正在载入第 {pageNumber} 页</div>}
      {error && <div className="pdf-page-render-state error">{error}</div>}
    </div>
  );
}

function boundedPageWindow(page: number, pageCount: number, radius: number): number[] {
  if (pageCount <= 0) return [];
  const safePage = Math.min(Math.max(1, page), pageCount);
  const start = Math.max(1, safePage - Math.max(0, radius));
  const end = Math.min(pageCount, safePage + Math.max(0, radius));
  return Array.from({ length: end - start + 1 }, (_, index) => start + index);
}

function paragraphAtClientPoint(
  readingMap: PageReadingMap,
  side: "source" | "translation",
  clientX: number,
  clientY: number,
  surfaceBounds: DOMRect,
  tolerance: number,
): ReadingParagraph | undefined {
  const pointX = ((clientX - surfaceBounds.left) / surfaceBounds.width) * readingMap.page.width;
  const pointY = ((clientY - surfaceBounds.top) / surfaceBounds.height) * readingMap.page.height;
  return readingMap.paragraphs.find((candidate) => {
    const boxes = side === "source" ? candidate.sourceBoxes : candidate.translationBoxes;
    return boxes.some(([x0, y0, x1, y1]) => (
      pointX >= x0 - tolerance
      && pointX <= x1 + tolerance
      && pointY >= y0 - tolerance
      && pointY <= y1 + tolerance
    ));
  });
}

function selectedTextWithinParagraph(
  selection: Selection | null,
  textLayer: HTMLDivElement | null,
  readingMap: PageReadingMap,
  side: "source" | "translation",
  paragraph: ReadingParagraph,
  surfaceBounds: DOMRect,
  tolerance: number,
): { text: string; anchor: SelectionAnchor } | null {
  if (!selection || selection.isCollapsed || selection.rangeCount !== 1 || !textLayer) return null;
  if (!selection.anchorNode || !selection.focusNode) return null;
  if (!textLayer.contains(selection.anchorNode) || !textLayer.contains(selection.focusNode)) return null;
  const range = selection.getRangeAt(0);
  const rectangles = Array.from(range.getClientRects()).filter((rectangle) => (
    rectangle.width > 0 && rectangle.height > 0
  ));
  if (rectangles.length === 0) return null;
  const allInsideParagraph = rectangles.every((rectangle) => (
    paragraphAtClientPoint(
      readingMap,
      side,
      rectangle.left + rectangle.width / 2,
      rectangle.top + rectangle.height / 2,
      surfaceBounds,
      tolerance,
    )?.id === paragraph.id
  ));
  if (!allInsideParagraph) return null;
  const text = selection.toString().replace(/\s+/g, " ").trim().slice(0, 300);
  if (!text) return null;
  return { text, anchor: selectionAnchorFromRectangles(rectangles, surfaceBounds) };
}

function hasNativeTextSelection(selection: Selection | null, textLayer: HTMLDivElement | null): boolean {
  return Boolean(
    selection
    && !selection.isCollapsed
    && selection.rangeCount === 1
    && selection.anchorNode
    && selection.focusNode
    && textLayer?.contains(selection.anchorNode)
    && textLayer.contains(selection.focusNode)
  );
}

function selectionAnchorFromRectangles(rectangles: DOMRect[], surfaceBounds: DOMRect): SelectionAnchor {
  const left = Math.min(...rectangles.map((rectangle) => rectangle.left)) - surfaceBounds.left;
  const top = Math.min(...rectangles.map((rectangle) => rectangle.top)) - surfaceBounds.top;
  const right = Math.max(...rectangles.map((rectangle) => rectangle.right)) - surfaceBounds.left;
  const bottom = Math.max(...rectangles.map((rectangle) => rectangle.bottom)) - surfaceBounds.top;
  const actionWidth = 86;
  const actionHeight = 28;
  const popupWidth = Math.min(320, Math.max(180, surfaceBounds.width - 16));
  const popupHeight = 150;
  const actionLeft = clamp(right + 6, 8, surfaceBounds.width - actionWidth - 8);
  const actionTop = clamp(top, 8, surfaceBounds.height - actionHeight - 8);
  const popoverLeft = clamp(actionLeft, 8, surfaceBounds.width - popupWidth - 8);
  const preferredPopoverTop = actionTop + actionHeight + 6;
  const popoverTop = preferredPopoverTop + popupHeight <= surfaceBounds.height - 8
    ? preferredPopoverTop
    : clamp(top - popupHeight - 6, 8, Math.max(8, bottom));
  return { actionLeft, actionTop, popoverLeft, popoverTop };
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), Math.max(minimum, maximum));
}

function boxStyle(
  box: PdfBox,
  page: PageReadingMap["page"],
): CSSProperties {
  const [x0, y0, x1, y1] = box;
  if (page.width <= 0 || page.height <= 0) return {};
  return {
    left: `${(x0 / page.width) * 100}%`,
    top: `${(y0 / page.height) * 100}%`,
    width: `${(Math.max(0, x1 - x0) / page.width) * 100}%`,
    height: `${(Math.max(0, y1 - y0) / page.height) * 100}%`,
  };
}
