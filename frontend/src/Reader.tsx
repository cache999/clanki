// PDF reader: pdf.js viewer with selectable text, plus clanki's highlight overlay.
import * as pdfjs from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import "pdfjs-dist/web/pdf_viewer.css";
import type { PDFViewer as PDFViewerT } from "pdfjs-dist/web/pdf_viewer.mjs";
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import type { Source } from "./api";
import { pageCoverage } from "./coverage";
import { boxFromDrag, renderScale } from "./figure";
import { hitTest, normaliseRects } from "./selection";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;
// The viewer module reads globalThis.pdfjsLib, which the pdfjs-dist import above sets.
const viewerLib = import("pdfjs-dist/web/pdf_viewer.mjs");

/** sourceId: the selection is a transcribed figure (that source), not text selected on the page. */
export type ReaderSelection = { page: number; text: string; rects: number[][]; sourceId?: string };
export type Region = { page: number; rect: number[]; image: string };

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
  currentPage(): number;
};

type Props = {
  url: string;
  sources: Source[];
  activeSourceId: string | null;
  sourcesWithCards: Set<string>;
  sourceStatus: Map<string, "pending" | "failed">;
  /** The document's cards, for the coverage strip. */
  notes: { source_id: string | null }[];
  selection: ReaderSelection | null;
  /** Replaces the selection hint in the reader bar (e.g. the generation focus box). */
  bar?: React.ReactNode;
  /** Dragging draws a box around a figure instead of selecting text. */
  regionMode: boolean;
  onRegion(r: Region): void;
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
    const { sources, activeSourceId, sourcesWithCards, sourceStatus } = propsRef.current;
    const layer = document.createElement("div");
    layer.className = "clanki-hl";
    for (const s of sources) {
      if (s.page !== pageNumber) continue;
      for (const [x, y, w, h] of s.rects) {
        const r = document.createElement("div");
        const state = sourceStatus.get(s.id);
        r.className =
          "hl" +
          (state ? " " + state : sourcesWithCards.has(s.id) ? " has-cards" : "") +
          (s.kind === "region" ? " region" : "") +
          (s.id === activeSourceId ? " active" : "");
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

  useEffect(redrawAll, [props.sources, props.activeSourceId, props.sourcesWithCards, props.sourceStatus]);

  /** The box rendered at about the resolution the model reads, as a PNG data URL. */
  async function capture(pageNumber: number, rect: number[]): Promise<string> {
    const pdfPage = viewerRef.current!.getPageView(pageNumber - 1).pdfPage;
    const base = pdfPage.getViewport({ scale: 1 });
    const vp = pdfPage.getViewport({ scale: renderScale(rect, base.width, base.height) });
    const [x, y, w, h] = rect;
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(w * vp.width));
    canvas.height = Math.max(1, Math.round(h * vp.height));
    await pdfPage.render({ canvas, viewport: vp, background: "white", transform: [1, 0, 0, 1, -x * vp.width, -y * vp.height] })
      .promise;
    return canvas.toDataURL("image/png");
  }

  function onMouseDown(e: React.MouseEvent) {
    if (!props.regionMode || e.button !== 0) return;
    const pageDiv = (e.target as HTMLElement).closest(".page") as HTMLElement | null;
    if (!pageDiv) return;
    e.preventDefault(); // no text selection while drawing
    const pageNumber = Number(pageDiv.dataset.pageNumber);
    const start = { x: e.clientX, y: e.clientY };
    const draft = document.createElement("div");
    draft.className = "region-draft";
    pageDiv.appendChild(draft);
    const box = () => pageBox(pageDiv);
    const show = (rect: number[] | null) => {
      const [x, y, w, h] = rect ?? [0, 0, 0, 0];
      Object.assign(draft.style, { left: `${x * 100}%`, top: `${y * 100}%`, width: `${w * 100}%`, height: `${h * 100}%` });
    };
    const move = (m: MouseEvent) => show(boxFromDrag(start, { x: m.clientX, y: m.clientY }, box()));
    const up = (m: MouseEvent) => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
      draft.remove();
      const rect = boxFromDrag(start, { x: m.clientX, y: m.clientY }, box());
      if (rect) void capture(pageNumber, rect).then((image) => propsRef.current.onRegion({ page: pageNumber, rect, image }));
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  }

  function onMouseUp(e: React.MouseEvent) {
    if (props.regionMode) return;
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
    currentPage() {
      return viewerRef.current?.currentPageNumber ?? 1;
    },
  }));

  const coverage = pageCoverage(page.count, props.sources, props.notes, props.sourceStatus);
  const sel = props.selection;
  return (
    <section className="reader">
      <div className="reader-bar">
        <span className="muted">
          p. {page.current}/{page.count || "…"}
        </span>
        {props.bar ? (
          props.bar
        ) : props.regionMode ? (
          <span className="sel-info">Drag a box around a figure or its labels to transcribe it · Esc cancels</span>
        ) : sel ? (
          <span className="sel-info">
            {sel.sourceId ? "Transcribed figure on" : "Selected on"} p.{sel.page}: “
            {sel.text.length > 60 ? sel.text.slice(0, 60) + "…" : sel.text}” —{" "}
            <kbd>G</kbd> generate · <kbd>N</kbd> card · <kbd>L</kbd> list · <kbd>Esc</kbd> clear
          </span>
        ) : (
          <span className="muted">Select text, then G to generate cards, or N / L to write one · Shift+G: whole document</span>
        )}
      </div>
      <div className="reader-body">
        {error && <div className="reader-error">Could not open the PDF: {error}</div>}
        <div
          ref={containerRef}
          className={`pdf-container${props.regionMode ? " region-mode" : ""}`}
          onMouseDown={onMouseDown}
          onMouseUp={onMouseUp}
        >
          <div className="pdfViewer" />
        </div>
        <div className="coverage" aria-label="Coverage">
          {coverage.map((c, i) => (
            <div
              key={i}
              className={`seg${c.state !== "empty" ? " " + c.state : ""}${i + 1 === page.current ? " current" : ""}`}
              style={c.state === "carded" ? { opacity: Math.min(1, 0.35 + c.cards / 6) } : undefined}
              title={`p.${i + 1}: ${Math.round(c.cards)} cards${c.state === "pending" ? ", generating" : c.state === "failed" ? ", generation failed" : ""}`}
              onClick={() => {
                if (viewerRef.current) viewerRef.current.currentPageNumber = i + 1;
              }}
            />
          ))}
        </div>
      </div>
    </section>
  );
});
