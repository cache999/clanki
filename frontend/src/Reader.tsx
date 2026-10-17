// PDF reader: pdf.js viewer with selectable text, plus clanki's highlight overlay.
import * as pdfjs from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import "pdfjs-dist/web/pdf_viewer.css";
import type { PDFViewer as PDFViewerT } from "pdfjs-dist/web/pdf_viewer.mjs";
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import type { Source } from "./api";
import { hitTest, normaliseRects } from "./selection";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;
// The viewer module reads globalThis.pdfjsLib, which the pdfjs-dist import above sets.
const viewerLib = import("pdfjs-dist/web/pdf_viewer.mjs");

export type ReaderSelection = { page: number; text: string; rects: number[][] };

/** The page's padding box in client coordinates. pdf.js pages have a border, and the
 * highlight layer (like the text layer) is positioned inside it. */
function pageBox(div: HTMLElement) {
  const r = div.getBoundingClientRect();
  return { left: r.left + div.clientLeft, top: r.top + div.clientTop, width: div.clientWidth, height: div.clientHeight };
}

export type ReaderHandle = {
  prevPage(): void;
  nextPage(): void;
  zoomIn(): void;
  zoomOut(): void;
  zoomFit(): void;
  showSource(sourceId: string): void;
  clearSelection(): void;
};

type Props = {
  url: string;
  sources: Source[];
  activeSourceId: string | null;
  sourcesWithCards: Set<string>;
  selection: ReaderSelection | null;
  onSelection(sel: ReaderSelection | null): void;
  onSourceClick(sourceId: string): void;
};

export const Reader = forwardRef<ReaderHandle, Props>(function Reader(props, ref) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<PDFViewerT | null>(null);
  const propsRef = useRef(props);
  propsRef.current = props;
  const [page, setPage] = useState({ current: 1, count: 0 });
  const [error, setError] = useState<string | null>(null);

  function drawHighlights(pageNumber: number) {
    const view = viewerRef.current?.getPageView(pageNumber - 1);
    const div: HTMLElement | undefined = view?.div;
    if (!div) return;
    div.querySelector(".clanki-hl")?.remove();
    const { sources, activeSourceId, sourcesWithCards } = propsRef.current;
    const layer = document.createElement("div");
    layer.className = "clanki-hl";
    for (const s of sources) {
      if (s.page !== pageNumber) continue;
      for (const [x, y, w, h] of s.rects) {
        const r = document.createElement("div");
        r.className = "hl" + (sourcesWithCards.has(s.id) ? " has-cards" : "") + (s.id === activeSourceId ? " active" : "");
        Object.assign(r.style, { left: `${x * 100}%`, top: `${y * 100}%`, width: `${w * 100}%`, height: `${h * 100}%` });
        layer.appendChild(r);
      }
    }
    // Under the transparent text layer, above the canvas, so selection still works.
    const text = div.querySelector(".textLayer");
    div.insertBefore(layer, text);
  }

  function redrawAll() {
    const v = viewerRef.current;
    if (!v) return;
    for (let i = 1; i <= v.pagesCount; i++) drawHighlights(i);
  }

  useEffect(() => {
    let cancelled = false;
    let task: pdfjs.PDFDocumentLoadingTask | null = null;
    setError(null);
    (async () => {
      const { EventBus, PDFLinkService, PDFViewer } = await viewerLib;
      if (cancelled || !containerRef.current) return;
      const eventBus = new EventBus();
      const linkService = new PDFLinkService({ eventBus });
      const viewer = new PDFViewer({ container: containerRef.current, eventBus, linkService });
      linkService.setViewer(viewer);
      viewerRef.current = viewer;
      eventBus.on("pagesinit", () => {
        viewer.currentScaleValue = "page-width";
        setPage({ current: 1, count: viewer.pagesCount });
      });
      eventBus.on("pagechanging", (e: { pageNumber: number }) =>
        setPage((p) => ({ ...p, current: e.pageNumber })),
      );
      eventBus.on("textlayerrendered", (e: { pageNumber: number }) => drawHighlights(e.pageNumber));
      task = pdfjs.getDocument({ url: props.url });
      let doc: pdfjs.PDFDocumentProxy;
      try {
        doc = await task.promise;
      } catch (e) {
        if (!cancelled) setError(String(e));
        return;
      }
      if (cancelled) return;
      viewer.setDocument(doc);
      linkService.setDocument(doc);
    })();
    return () => {
      cancelled = true;
      viewerRef.current?.setDocument(null as never);
      viewerRef.current = null;
      void task?.destroy();
    };
  }, [props.url]);

  useEffect(redrawAll, [props.sources, props.activeSourceId, props.sourcesWithCards]);

  function onMouseUp(e: React.MouseEvent) {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) {
      // A plain click: select the cards of a highlight under the pointer.
      const pageDiv = (e.target as HTMLElement).closest(".page") as HTMLElement | null;
      if (!pageDiv) return;
      const pageNumber = Number(pageDiv.dataset.pageNumber);
      const box = pageBox(pageDiv);
      const x = (e.clientX - box.left) / box.width;
      const y = (e.clientY - box.top) / box.height;
      const hit = props.sources.find((s) => s.page === pageNumber && hitTest(s.rects, x, y));
      if (hit) props.onSourceClick(hit.id);
      return;
    }
    const range = sel.getRangeAt(0);
    const start = range.startContainer instanceof Element ? range.startContainer : range.startContainer.parentElement;
    const pageDiv = start?.closest(".page") as HTMLElement | null;
    if (!pageDiv || !containerRef.current?.contains(pageDiv)) return;
    const text = sel.toString().trim();
    if (!text) return;
    props.onSelection({
      page: Number(pageDiv.dataset.pageNumber),
      text,
      rects: normaliseRects([...range.getClientRects()], pageBox(pageDiv)),
    });
  }

  useImperativeHandle(ref, () => ({
    prevPage() {
      const v = viewerRef.current;
      if (v && v.currentPageNumber > 1) v.currentPageNumber -= 1;
    },
    nextPage() {
      const v = viewerRef.current;
      if (v && v.currentPageNumber < v.pagesCount) v.currentPageNumber += 1;
    },
    zoomIn() {
      if (viewerRef.current) viewerRef.current.currentScale = Math.min(viewerRef.current.currentScale * 1.15, 5);
    },
    zoomOut() {
      if (viewerRef.current) viewerRef.current.currentScale = Math.max(viewerRef.current.currentScale / 1.15, 0.25);
    },
    zoomFit() {
      if (viewerRef.current) viewerRef.current.currentScaleValue = "page-width";
    },
    showSource(sourceId) {
      const s = propsRef.current.sources.find((x) => x.id === sourceId);
      const c = containerRef.current;
      const div: HTMLElement | undefined = s && viewerRef.current?.getPageView(s.page - 1)?.div;
      if (!s || !c || !div) return;
      const y = s.rects.length ? s.rects[0][1] : 0;
      c.scrollTo({ top: div.offsetTop + div.clientTop + y * div.clientHeight - c.clientHeight / 3, behavior: "smooth" });
    },
    clearSelection() {
      window.getSelection()?.removeAllRanges();
    },
  }));

  const sel = props.selection;
  return (
    <section className="reader">
      <div className="reader-bar">
        <span className="muted">
          p. {page.current}/{page.count || "…"}
        </span>
        {sel ? (
          <span className="sel-info">
            Selected on p.{sel.page}: “{sel.text.length > 60 ? sel.text.slice(0, 60) + "…" : sel.text}” —{" "}
            <kbd>N</kbd> card · <kbd>L</kbd> list · <kbd>Esc</kbd> clear
          </span>
        ) : (
          <span className="muted">Select text, then press N for a card or L for a list</span>
        )}
      </div>
      <div className="reader-body">
        {error && <div className="reader-error">Could not open the PDF: {error}</div>}
        <div ref={containerRef} className="pdf-container" onMouseUp={onMouseUp}>
          <div className="pdfViewer" />
        </div>
      </div>
    </section>
  );
});
