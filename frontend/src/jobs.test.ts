import { describe, expect, it } from "vitest";
import { cardDiff, jobSummary, openEdits, pagesLabel, sourceStates } from "./jobs";

const j = (status: string, cost = 0, source_id = "s") => ({ status, cost_usd: cost, source_id });

describe("jobSummary", () => {
  it("counts active and failed jobs and totals the cost", () => {
    expect(jobSummary([j("running", 0.001), j("queued"), j("failed", 0.002), j("done", 0.003)])).toEqual({
      active: 2,
      failed: 1,
      cost: 0.006,
    });
  });
});

describe("pagesLabel", () => {
  it("shows one page or a range", () => {
    expect(pagesLabel([3, 3])).toBe("p.3");
    expect(pagesLabel([1, 6])).toBe("p.1–6");
  });
});

describe("sourceStates", () => {
  it("marks highlights with a pending or failed job, newest job winning", () => {
    // jobs arrive newest first
    const m = sourceStates([j("done", 0, "a"), j("failed", 0, "a"), j("running", 0, "b"), j("failed", 0, "c")]);
    expect(Object.fromEntries(m)).toEqual({ b: "pending", c: "failed" });
  });
});

describe("edit jobs", () => {
  const e = (status: string, note_id: string, extra = {}) => ({ status, cost_usd: 0, source_id: "s", mode: "edit", note_id, ...extra });

  it("do not colour highlights", () => {
    expect(sourceStates([e("running", "n1"), e("failed", "n2")]).size).toBe(0);
  });

  it("give each card its newest open suggestion", () => {
    const jobs = [e("discarded", "n1"), e("done", "n1", { id: "old" }), e("running", "n2"), e("applied", "n3")];
    const m = openEdits(jobs);
    expect([...m.keys()].sort()).toEqual(["n1", "n2"]);
    expect(m.get("n1")!.status).toBe("done");
  });
});

describe("cardDiff", () => {
  it("lists the fields a suggestion changes", () => {
    const before = { type: "qa", front: "Long front", back: "~498 nm", why: "", add_reverse: false, reverse_prompt: "" };
    const after = { type: "qa", front: "Short", back: "~498 nm", why: "Rods.", add_reverse: true, reverse_prompt: "pigment?" };
    expect(cardDiff(before, after)).toEqual([
      { label: "Front", old: "Long front", new: "Short" },
      { label: "Reverse", old: "off", new: "on" },
      { label: "Reverse prompt", old: "", new: "pigment?" },
      { label: "Why", old: "", new: "Rods." },
    ]);
  });

  it("shows list items and type changes", () => {
    const before = { type: "qa", front: "Layers", back: "a; b" };
    const after = { type: "list", title: "Layers (outer to inner)", items: ["a", "b"], remarks: "" };
    expect(cardDiff(before, after).map((d) => d.label)).toEqual(["Type", "Title", "Items"]);
  });

  it("shows a cloze's text and extra", () => {
    const before = { type: "qa", front: "Rhodopsin peak", back: "~498 nm" };
    const after = { type: "cloze", text: "Rhodopsin peaks near {{c1::~498 nm}}", why: "Rods." };
    expect(cardDiff(before, after)).toEqual([
      { label: "Type", old: "Q/A", new: "Cloze" },
      { label: "Text", old: "", new: "Rhodopsin peaks near {{c1::~498 nm}}" },
      { label: "Extra", old: "", new: "Rods." },
    ]);
  });
});
