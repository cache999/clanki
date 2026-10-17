// Geometry and text helpers for turning a reader selection into a highlight and a card.

export type Rect = { left: number; top: number; width: number; height: number };

const round = (x: number) => Math.round(x * 1e4) / 1e4;

/** Client rects of a selection -> [x, y, w, h] fractions of the page box. Rects on the same
 * line that touch are merged, so a highlight is one bar per line. */
export function normaliseRects(rects: Rect[], page: Rect): number[][] {
  const right = page.left + page.width;
  const bottom = page.top + page.height;
  const boxes = rects
    .map((r) => ({
      l: Math.max(r.left, page.left),
      t: Math.max(r.top, page.top),
      r: Math.min(r.left + r.width, right),
      b: Math.min(r.top + r.height, bottom),
    }))
    .filter((b) => b.r - b.l > 0.5 && b.b - b.t > 0.5)
    .sort((a, b) => a.t - b.t || a.l - b.l);
  const merged: typeof boxes = [];
  for (const b of boxes) {
    const last = merged[merged.length - 1];
    const sameLine = last && Math.abs(b.t - last.t) < (last.b - last.t) / 2;
    if (last && sameLine && b.l <= last.r + 2) {
      last.l = Math.min(last.l, b.l);
      last.t = Math.min(last.t, b.t);
      last.r = Math.max(last.r, b.r);
      last.b = Math.max(last.b, b.b);
    } else merged.push({ ...b });
  }
  return merged.map((b) => [
    round((b.l - page.left) / page.width),
    round((b.t - page.top) / page.height),
    round((b.r - b.l) / page.width),
    round((b.b - b.t) / page.height),
  ]);
}

export function hitTest(rects: number[][], x: number, y: number): boolean {
  return rects.some(([rx, ry, w, h]) => x >= rx && x <= rx + w && y >= ry && y <= ry + h);
}

const BULLET = /^\s*(?:[•●▪◦‣\-–—*]|\(?\d{1,2}[.)]|\(?[a-zA-Z][.)])\s+/;

const lines = (text: string) =>
  text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);

/** Selected text -> one paragraph: PDF line wraps carry no meaning. */
export function joinLines(text: string): string {
  return lines(text).join(" ").replace(/\s+/g, " ");
}

/** Selected text -> list items, bullets and numbering removed. A line without a marker
 * continues the previous item when other lines have markers, or when it starts in lower case
 * (a wrapped line). */
export function splitItems(text: string): string[] {
  const ls = lines(text);
  const marked = ls.map((l) => BULLET.test(l));
  const anyMarked = marked.some(Boolean);
  const items: string[] = [];
  ls.forEach((l, i) => {
    const body = l.replace(BULLET, "").trim();
    if (items.length && !marked[i] && (anyMarked || /^[a-z]/.test(body))) items[items.length - 1] += " " + body;
    else items.push(body);
  });
  return items.filter(Boolean);
}

/** Cards in reading order: by the page of their highlight; cards without one go last. */
export function orderNotes<N extends { id: string; source_id: string | null }>(
  notes: N[],
  sources: { id: string; page: number }[],
): N[] {
  const page = new Map(sources.map((s) => [s.id, s.page]));
  const key = (n: N) => (n.source_id && page.has(n.source_id) ? page.get(n.source_id)! : Infinity);
  return notes
    .map((n, i) => ({ n, i }))
    .sort((a, b) => key(a.n) - key(b.n) || a.i - b.i)
    .map((x) => x.n);
}
