// Figures: a box dragged on a page (or a pasted screenshot) is read by the model into text.
import { pagesLabel } from "./jobs";

type Point = { x: number; y: number };
type Box = { left: number; top: number; width: number; height: number };

const MIN_DRAG_PX = 8;
const MODEL_PIXELS = 1300 * 1300; // deepseek-flash scales larger images down to this

/** The dragged box as [x, y, w, h] fractions of the page, or null for a click. */
export function boxFromDrag(a: Point, b: Point, page: Box): number[] | null {
  if (Math.abs(a.x - b.x) < MIN_DRAG_PX || Math.abs(a.y - b.y) < MIN_DRAG_PX) return null;
  const fx = (x: number) => Math.min(1, Math.max(0, (x - page.left) / page.width));
  const fy = (y: number) => Math.min(1, Math.max(0, (y - page.top) / page.height));
  const [x0, x1] = [fx(a.x), fx(b.x)].sort((p, q) => p - q);
  const [y0, y1] = [fy(a.y), fy(b.y)].sort((p, q) => p - q);
  const r = (v: number) => Math.round(v * 1e4) / 1e4;
  return [r(x0), r(y0), r(x1 - x0), r(y1 - y0)];
}

/** pdf.js scale that renders the box (page size in points) at about the pixels the model reads. */
export function renderScale([, , w, h]: number[], pageWidth: number, pageHeight: number): number {
  const s = Math.sqrt(MODEL_PIXELS / (w * pageWidth * h * pageHeight));
  return Math.min(6, Math.max(1.5, s));
}

export function sourceLabel(s: { kind: string; page: number; page_end: number | null }): string {
  const pages = pagesLabel([s.page, s.page_end ?? s.page]);
  const what: Record<string, string> = { region: " figure", image: " image", prompt: " prompt" };
  return pages + (what[s.kind] ?? "");
}

/** The transcripts of several screenshots as one text, each labelled with where it came from. */
export function joinTranscripts(shots: { page: number; text: string }[]): string {
  if (shots.length === 1) return shots[0].text.trim();
  return shots.map((s, i) => `[Image ${i + 1}, p.${s.page}]\n${s.text.trim()}`).join("\n\n");
}

/** The screenshot selection after a click: just this one, or with Shift, this one added or removed. */
export function pickShot(selected: string[], id: string, shift: boolean): string[] {
  if (!shift) return [id];
  return selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id];
}

/** The drag-and-drop type of a screenshot dragged from the tray (its source id). */
export const SHOT_TYPE = "application/x-clanki-shot";

/** The fields a screenshot can be dropped on (media.IMAGE_FIELDS; a list's "why" is its Remarks). */
export function imageFields(type: "qa" | "list"): [string, string][] {
  return type === "qa" ? [["front", "Front"], ["back", "Back"], ["why", "Why"]] : [["why", "Remarks"], ["sources", "Sources"]];
}
