import { describe, expect, it } from "vitest";
import { SHORTCUTS, commandFor } from "./keys";

const k = (key: string, mods: Partial<Record<"ctrlKey" | "metaKey" | "altKey" | "shiftKey", boolean>> = {}) => ({
  key,
  ...mods,
});

describe("commandFor", () => {
  it("maps single letters", () => {
    expect(commandFor(k("n"), false)).toBe("newCard");
    expect(commandFor(k("l"), false)).toBe("newList");
    expect(commandFor(k("e"), false)).toBe("edit");
    expect(commandFor(k("s"), false)).toBe("send");
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
