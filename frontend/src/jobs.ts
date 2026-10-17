// Helpers for showing generation jobs.

type JobLike = { status: string; cost_usd: number; source_id: string | null };

export function jobSummary(jobs: JobLike[]) {
  const cost = jobs.reduce((s, j) => s + j.cost_usd, 0);
  return {
    active: jobs.filter((j) => j.status === "queued" || j.status === "running").length,
    failed: jobs.filter((j) => j.status === "failed").length,
    cost: Math.round(cost * 1e6) / 1e6,
  };
}

export function pagesLabel([a, b]: [number, number] | number[]): string {
  return a === b ? `p.${a}` : `p.${a}–${b}`;
}

/** Highlight state from each source's newest job (jobs arrive newest first): pending while
 * it runs, failed if it failed. Sources whose newest job succeeded are left to the cards. */
export function sourceStates(jobs: JobLike[]): Map<string, "pending" | "failed"> {
  const seen = new Set<string>();
  const out = new Map<string, "pending" | "failed">();
  for (const j of jobs) {
    if (!j.source_id || seen.has(j.source_id)) continue;
    seen.add(j.source_id);
    if (j.status === "queued" || j.status === "running") out.set(j.source_id, "pending");
    else if (j.status === "failed") out.set(j.source_id, "failed");
  }
  return out;
}

export function money(usd: number): string {
  return usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(2)}`;
}
