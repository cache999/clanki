import { describe, expect, it } from "vitest";
import { hitTest, joinLines, normaliseRects, orderNotes, splitItems } from "./selection";

const page = { left: 100, top: 50, width: 400, height: 800 };

describe("normaliseRects", () => {
  it("converts client rects to page fractions", () => {
    expect(normaliseRects([{ left: 140, top: 130, width: 100, height: 16 }], page)).toEqual([[0.1, 0.1, 0.25, 0.02]]);
  });

  it("drops empty rects and rects outside the page, clips partial ones", () => {
    const r = normaliseRects(
      [
        { left: 140, top: 130, width: 0, height: 16 },
        { left: 600, top: 130, width: 50, height: 16 },
        { left: 80, top: 130, width: 60, height: 16 },
      ],
      page,
    );
    expect(r).toEqual([[0, 0.1, 0.1, 0.02]]);
  });

  it("merges touching rects on one line but not across lines", () => {
    const r = normaliseRects(
      [
        { left: 140, top: 130, width: 100, height: 16 },
        { left: 240, top: 131, width: 60, height: 15 },
        { left: 140, top: 150, width: 80, height: 16 },
      ],
      page,
    );
    expect(r).toEqual([
      [0.1, 0.1, 0.4, 0.02],
      [0.1, 0.125, 0.2, 0.02],
    ]);
  });
});

describe("hitTest", () => {
  it("finds a point inside any rect", () => {
    expect(hitTest([[0.1, 0.1, 0.25, 0.02]], 0.2, 0.11)).toBe(true);
    expect(hitTest([[0.1, 0.1, 0.25, 0.02]], 0.2, 0.2)).toBe(false);
  });
});

describe("joinLines", () => {
  it("turns PDF line wraps into spaces", () => {
    expect(joinLines("anatomy of eye, physiological\n optics;  accommodation\r\nand pupil")).toBe(
      "anatomy of eye, physiological optics; accommodation and pupil",
    );
  });
});

describe("splitItems", () => {
  it("joins wrapped lines onto the numbered item they continue", () => {
    const sel =
      "Light, contrast and the retinal image: Light and contrast; anatomy of eye, physiological\n" +
      "optics; accommodation and pupil\n" +
      "2. Visual pigments: Rhodopsin, phototransduction &\n" +
      "Its relation to hereditary retinal disease\n" +
      "3. Retinal processing";
    expect(splitItems(sel)).toEqual([
      "Light, contrast and the retinal image: Light and contrast; anatomy of eye, physiological optics; accommodation and pupil",
      "Visual pigments: Rhodopsin, phototransduction & Its relation to hereditary retinal disease",
      "Retinal processing",
    ]);
  });

  it("without markers, joins lines that start in lower case", () => {
    expect(splitItems("Rods detect dim light and\nare absent from the fovea\nCones need bright light")).toEqual([
      "Rods detect dim light and are absent from the fovea",
      "Cones need bright light",
    ]);
  });

  it("splits lines and strips bullets and numbering", () => {
    expect(splitItems("• Rods\n- Cones\n\n2. Bipolar cells\n a) Ganglion cells \n–  Amacrine")).toEqual([
      "Rods",
      "Cones",
      "Bipolar cells",
      "Ganglion cells",
      "Amacrine",
    ]);
  });
});

describe("orderNotes", () => {
  it("orders by source page, keeps creation order within a page, sourceless last", () => {
    const sources = [
      { id: "s5", page: 5 },
      { id: "s2", page: 2 },
    ];
    const notes = [
      { id: "a", source_id: "s5" },
      { id: "b", source_id: null },
      { id: "c", source_id: "s2" },
      { id: "d", source_id: "s5" },
    ];
    expect(orderNotes(notes, sources).map((n) => n.id)).toEqual(["c", "a", "d", "b"]);
  });
});
