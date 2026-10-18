import { describe, expect, it } from "vitest";
import { boxFromDrag, renderScale, sourceLabel } from "./figure";

const page = { left: 100, top: 50, width: 400, height: 600 };

describe("boxFromDrag", () => {
  it("gives [x, y, w, h] as fractions of the page, whichever way the drag went", () => {
    expect(boxFromDrag({ x: 300, y: 350 }, { x: 100 + 40, y: 50 + 60 }, page)).toEqual([0.1, 0.1, 0.4, 0.4]);
  });

  it("clamps to the page", () => {
    expect(boxFromDrag({ x: 0, y: 0 }, { x: 300, y: 350 }, page)).toEqual([0, 0, 0.5, 0.5]);
  });

  it("ignores a click or a tiny drag", () => {
    expect(boxFromDrag({ x: 200, y: 200 }, { x: 203, y: 202 }, page)).toBeNull();
  });
});

describe("renderScale", () => {
  it("renders the box at about 1300×1300 pixels' worth, the most the model reads", () => {
    const s = renderScale([0, 0, 0.5, 0.5], 600, 800); // a 300×400 pt box
    expect(300 * s * 400 * s).toBeCloseTo(1300 * 1300, -3);
  });

  it("stays between 1.5× and 6×", () => {
    expect(renderScale([0, 0, 1, 1], 2000, 3000)).toBe(1.5);
    expect(renderScale([0, 0, 0.02, 0.02], 600, 800)).toBe(6);
  });
});

describe("sourceLabel", () => {
  it("says where a card came from", () => {
    expect(sourceLabel({ kind: "highlight", page: 3, page_end: null })).toBe("p.3");
    expect(sourceLabel({ kind: "chunk", page: 3, page_end: 6 })).toBe("p.3–6");
    expect(sourceLabel({ kind: "region", page: 3, page_end: null })).toBe("p.3 figure");
    expect(sourceLabel({ kind: "image", page: 3, page_end: null })).toBe("p.3 image");
  });
});
