import { describe, expect, it } from "vitest";
import { SHORTCUTS, commandFor, submits } from "./keys";

const k = (key: string, mods: Partial<Record<"ctrlKey" | "metaKey" | "altKey" | "shiftKey", boolean>> = {}) => ({
  key,
  ...mods,
});

describe("commandFor", () => {
  it("maps single letters", () => {
    expect(commandFor(k("v"), false)).toBe("newCloze");
    expect(commandFor(k("b"), false)).toBe("figure");
    expect(commandFor(k("B", { shiftKey: true }), false)).toBe("figureRead");
    expect(commandFor(k("n"), false)).toBe("newCard");
    expect(commandFor(k("l"), false)).toBe("newList");
    expect(commandFor(k("e"), false)).toBe("edit");
  });

  it("is case-insensitive for letters but respects Shift", () => {
    expect(commandFor(k("E", { shiftKey: true }), false)).toBe("export");
    expect(commandFor(k("N", { shiftKey: true }), false)).toBeNull();
  });

  it("maps generation, jobs and settings", () => {
    expect(commandFor(k("g"), false)).toBe("generate");
    expect(commandFor(k("G", { shiftKey: true }), false)).toBe("generateDocument");
    expect(commandFor(k("."), false)).toBe("jobs");
    expect(commandFor(k(","), false)).toBe("settings");
  });

  it("matches symbols regardless of Shift", () => {
    expect(commandFor(k("?", { shiftKey: true }), false)).toBe("help");
    expect(commandFor(k("+", { shiftKey: true }), false)).toBe("zoomIn");
    expect(commandFor(k("="), false)).toBe("zoomIn");
    expect(commandFor(k("]"), false)).toBe("nextPage");
  });

  it("supports alternatives and Ctrl/Cmd", () => {
    expect(commandFor(k("ArrowDown"), false)).toBe("next");
    expect(commandFor(k("k"), false)).toBe("prev");
    expect(commandFor(k("z", { ctrlKey: true }), false)).toBe("undo");
    expect(commandFor(k("z", { metaKey: true }), false)).toBe("undo");
    expect(commandFor(k("Delete"), false)).toBe("delete");
  });

  it("ignores browser combos and keys while typing", () => {
    expect(commandFor(k("n", { ctrlKey: true }), false)).toBeNull();
    expect(commandFor(k("n", { altKey: true }), false)).toBeNull();
    expect(commandFor(k("n"), true)).toBeNull();
  });

  it("has no duplicate bindings", () => {
    const all = SHORTCUTS.flatMap((s) => s.keys.map((key) => key.toLowerCase()));
    expect(new Set(all).size).toBe(all.length);
  });
});

describe("left-hand keys (the right hand stays on the mouse)", () => {
  it("puts the daily actions on the left", () => {
    expect(commandFor(k("c"), false)).toBe("newCard");
    expect(commandFor(k("C", { shiftKey: true }), false)).toBe("newList");
    expect(commandFor(k("b"), false)).toBe("figure");
    expect(commandFor(k("q"), false)).toBe("promptCard");
    expect(commandFor(k("f"), false)).toBe("acceptSuggestion");
    expect(commandFor(k("d"), false)).toBe("discardSuggestion");
    expect(commandFor(k("`"), false)).toBe("jobs");
  });

  it("moves between cards with Tab and Shift+Tab", () => {
    expect(commandFor(k("Tab"), false)).toBe("next");
    expect(commandFor(k("Tab", { shiftKey: true }), false)).toBe("prev");
    expect(commandFor(k("Tab", { altKey: true }), false)).toBeNull();
    expect(commandFor(k("Tab", { ctrlKey: true }), false)).toBeNull();
  });

  it("keeps the old keys working", () => {
    expect(commandFor(k("n"), false)).toBe("newCard");
    expect(commandFor(k("l"), false)).toBe("newList");
    expect(commandFor(k("i"), false)).toBe("figure");
    expect(commandFor(k("p"), false)).toBe("promptCard");
    expect(commandFor(k("y"), false)).toBe("acceptSuggestion");
    expect(commandFor(k("j"), false)).toBe("next");
    expect(commandFor(k("."), false)).toBe("jobs");
  });

  it("needs Shift to send, so a stray S next to D and F sends nothing", () => {
    expect(commandFor(k("s"), false)).toBeNull();
    expect(commandFor(k("S", { shiftKey: true }), false)).toBe("send");
  });
});

describe("submits", () => {
  it("submits a one-line box with Enter, Tab or Ctrl+S", () => {
    expect(submits(k("Enter"), "line")).toBe(true);
    expect(submits(k("Tab"), "line")).toBe(true);
    expect(submits(k("s", { ctrlKey: true }), "line")).toBe(true);
    expect(submits(k("Tab", { shiftKey: true }), "line")).toBe(false);
    expect(submits(k("s"), "line")).toBe(false);
  });

  it("saves the card editor and the transcript with Ctrl+S or Ctrl+Enter; Tab moves between fields", () => {
    expect(submits(k("s", { ctrlKey: true }), "multiline")).toBe(true);
    expect(submits(k("S", { ctrlKey: true }), "multiline")).toBe(true);
    expect(submits(k("Enter", { metaKey: true }), "multiline")).toBe(true);
    expect(submits(k("Enter"), "multiline")).toBe(false);
    expect(submits(k("Tab"), "multiline")).toBe(false);
  });
});

describe("AI edit keys", () => {
  it("maps ask, accept and discard", () => {
    expect(commandFor({ key: "a" }, false)).toBe("aiEdit");
    expect(commandFor({ key: "y" }, false)).toBe("acceptSuggestion");
    expect(commandFor({ key: "d" }, false)).toBe("discardSuggestion");
  });
});
