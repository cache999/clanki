// Helpers for showing generation jobs.

type JobLike = { status: string; cost_usd: number; source_id: string | null; mode?: string; note_id?: string | null };

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
    if (!j.source_id || j.mode === "edit" || seen.has(j.source_id)) continue;
    seen.add(j.source_id);
    if (j.status === "queued" || j.status === "running") out.set(j.source_id, "pending");
    else if (j.status === "failed") out.set(j.source_id, "failed");
  }
  return out;
}

export function money(usd: number): string {
  return usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(2)}`;
}

const OPEN = new Set(["queued", "running", "done", "failed"]);

/** Each card's newest AI edit that still needs attention (running, or a suggestion or error to act on). */
export function openEdits<J extends JobLike>(jobs: J[]): Map<string, J> {
  const out = new Map<string, J>();
  for (const j of jobs) if (j.mode === "edit" && j.note_id && OPEN.has(j.status) && !out.has(j.note_id)) out.set(j.note_id, j);
  return out;
}

type CardFields = {
  type: string;
  front?: string;
  back?: string;
  add_reverse?: boolean;
  reverse_prompt?: string;
  why?: string;
  remarks?: string;
  title?: string;
  items?: string[];
  mnemonic?: string;
  full?: boolean;
  text?: string;
};

const TYPE_LABELS: Record<string, string> = { qa: "Q/A", list: "List", cloze: "Cloze" };

/** Fields a suggested card changes, as text, compared with the card as it is. `before` is a note
 * (lists keep remarks in why); `after` is a card in the model's reply format. */
export function cardDiff(before: CardFields, after: CardFields) {
  const onOff = (b: boolean | undefined) => (b ? "on" : "off");
  const txt = (s: string | undefined) => s ?? "";
  const rows: [string, string, string][] = [];
  if (before.type !== after.type) rows.push(["Type", TYPE_LABELS[before.type], TYPE_LABELS[after.type]]);
  if (after.type === "cloze") {
    rows.push(["Text", txt(before.text), txt(after.text)]);
    rows.push(["Extra", txt(before.why), txt(after.why)]);
  } else if (after.type === "qa") {
    rows.push(["Front", txt(before.front), txt(after.front)]);
    rows.push(["Back", txt(before.back), txt(after.back)]);
    rows.push(["Reverse", onOff(before.add_reverse), onOff(after.add_reverse)]);
    rows.push(["Reverse prompt", txt(before.reverse_prompt), txt(after.reverse_prompt)]);
    rows.push(["Why", txt(before.why), txt(after.why)]);
  } else {
    rows.push(["Title", txt(before.title), txt(after.title)]);
    rows.push(["Items", (before.items ?? []).join("; "), (after.items ?? []).join("; ")]);
    rows.push(["Remarks", txt(before.why), txt(after.remarks)]);
    rows.push(["Mnemonic", txt(before.mnemonic), txt(after.mnemonic)]);
    rows.push(["Whole-list card", onOff(before.full ?? true), onOff(after.full ?? true)]);
  }
  return rows.filter(([, o, n]) => o !== n).map(([label, o, n]) => ({ label, old: o, new: n }));
}
