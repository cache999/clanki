import { describe, expect, it } from "vitest";
import { jobSummary, pagesLabel, sourceStates } from "./jobs";

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
