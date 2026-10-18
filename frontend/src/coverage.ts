// Coverage strip: how much of each page has been carded, for the strip beside the reader.

type SourceLike = { id: string; page: number; page_end: number | null };
type NoteLike = { source_id: string | null };
export type PageCoverage = { cards: number; state: "pending" | "failed" | "carded" | "empty" };

/** Per page (index 0 = page 1): the cards made from it (a chunk's cards are spread evenly over its
 * pages) and its state; running generation shows over a failure, a failure over cards. */
export function pageCoverage(
  pageCount: number,
  sources: SourceLike[],
  notes: NoteLike[],
  sourceStatus: Map<string, "pending" | "failed">,
): PageCoverage[] {
  const pages = Array.from({ length: pageCount }, () => ({ cards: 0, pending: false, failed: false }));
  const byId = new Map(sources.map((s) => [s.id, s]));
  const span = (s: SourceLike) => {
    const out = [];
    for (let p = s.page; p <= (s.page_end ?? s.page); p++) if (p >= 1 && p <= pageCount) out.push(pages[p - 1]);
    return out;
  };
  for (const n of notes) {
    const s = n.source_id ? byId.get(n.source_id) : undefined;
    if (s) for (const p of span(s)) p.cards += 1 / ((s.page_end ?? s.page) - s.page + 1);
  }
  for (const [id, state] of sourceStatus) {
    const s = byId.get(id);
    if (s) for (const p of span(s)) p[state] = true;
  }
  return pages.map((p) => ({
    cards: p.cards,
    state: p.pending ? "pending" : p.failed ? "failed" : p.cards > 0 ? "carded" : "empty",
  }));
}
