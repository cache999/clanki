import { describe, expect, it } from "vitest";
import { pageCoverage } from "./coverage";

const src = (id: string, page: number, page_end: number | null = null) => ({ id, page, page_end });

describe("pageCoverage", () => {
  it("counts each page's cards, spreading a chunk's cards over its pages", () => {
    const sources = [src("h1", 1), src("c1", 2, 3)];
    const notes = [{ source_id: "h1" }, { source_id: "h1" }, { source_id: "c1" }, { source_id: "c1" }, { source_id: null }];
    expect(pageCoverage(4, sources, notes, new Map()).map((p) => p.cards)).toEqual([2, 1, 1, 0]);
  });

  it("marks pages with running or failed generation", () => {
    const sources = [src("h1", 1), src("c1", 2, 3)];
    const states = new Map<string, "pending" | "failed">([["h1", "failed"], ["c1", "pending"]]);
    expect(pageCoverage(3, sources, [], states).map((p) => p.state)).toEqual(["failed", "pending", "pending"]);
  });

  it("calls a page with cards carded, and one without anything empty", () => {
    expect(pageCoverage(2, [src("h1", 2)], [{ source_id: "h1" }], new Map()).map((p) => p.state)).toEqual(["empty", "carded"]);
  });

  it("leaves out cards from a prompt: they are not from the page they were asked on", () => {
    const sources = [{ ...src("p1", 1), kind: "prompt" }];
    const states = new Map<string, "pending" | "failed">([["p1", "pending"]]);
    expect(pageCoverage(1, sources, [{ source_id: "p1" }], states)).toEqual([{ cards: 0, state: "empty" }]);
  });

  it("ignores sources outside the document and cards whose source is unknown", () => {
    expect(pageCoverage(1, [src("h1", 5)], [{ source_id: "h1" }, { source_id: "gone" }], new Map())).toEqual([
      { cards: 0, state: "empty" },
    ]);
  });
});
