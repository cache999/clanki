// Typed wrappers around the clanki HTTP API (src/clanki/app.py).

export type Issue = { level: "error" | "warning"; code: string; message: string };

export type Note = {
  id: string;
  guid: string;
  document_id: string | null;
  source_id: string | null;
  type: "qa" | "list";
  front: string;
  back: string;
  add_reverse: boolean;
  reverse_prompt: string;
  title: string;
  items: string[];
  full: boolean;
  style: "div" | "ul";
  mnemonic: string;
  sources: string;
  why: string;
  deck: string;
  tags: string[];
  status: "new" | "sent" | "edited" | "exported"; // exported: imported into Anki from an export file
  anki_note_id: number | null;
  created_at: string;
  kind: string;
  facets: string[];
  flags: string[];
  issues: Issue[];
};

export type NoteDraft = Partial<Omit<Note, "id" | "issues" | "status" | "anki_note_id">> & {
  type: Note["type"];
};

export type Doc = {
  id: string;
  title: string;
  filename: string;
  kind: string;
  profile: string; // the prompt profile its cards are written with
  deck: string;
  tags: string[];
};

/** A highlight, or a page range used for whole-document generation (kind "chunk", no rects).
 * rects are [x, y, w, h] as fractions of the page box. */
export type Source = {
  id: string;
  document_id: string;
  kind: "highlight" | "chunk" | "region" | "image"; // region: a box around a figure; image: a pasted screenshot
  page: number;
  page_end: number | null;
  text: string;
  rects: number[][];
};

/** A card in the model's reply format (lists keep their Why in remarks). */
export type ProposedCard = {
  type: "qa" | "list";
  kind?: string;
  front?: string;
  back?: string;
  why?: string;
  add_reverse?: boolean;
  reverse_prompt?: string;
  title?: string;
  items?: string[];
  remarks?: string;
  mnemonic?: string;
  full?: boolean;
  flags?: string[];
};

export type Job = {
  id: string;
  document_id: string;
  source_id: string | null;
  note_id: string | null;
  mode: "highlight" | "chunk" | "edit" | "figure" | "transcribe";
  pages: [number, number];
  target: string;
  focus: string;
  model: string;
  profile: string;
  status: "queued" | "running" | "done" | "failed" | "cancelled" | "applied" | "discarded";
  error: string | null;
  attempts: number;
  usage: { cache_hit: number; cache_miss: number; output: number; reasoning: number };
  cost_usd: number;
  note_ids: string[];
  left_out: { text: string; reason: string }[];
  flags: string[];
  image_occlusion: string[];
  proposal: ProposedCard[];
  before: Partial<Note> | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type Estimate = {
  chunks: number;
  input_tokens: number;
  output_tokens: number;
  model: string;
  cost_usd: number;
  peak: boolean;
};

/** store: false where there is no credential store (WSL), so only the environment variable works. */
export type KeyStatus = { set: boolean; source: "env" | "keyring" | null; hint: string | null; store: boolean };
export type Settings = {
  providers: { deepseek: { models: string[]; key: KeyStatus } };
  default_model: string;
  /** The subquestion vocabulary the prompt uses: the profile's, plus the student's frequent ones. */
  facets: string[];
  /** For new documents; kept with the data. */
  defaults: { deck: string; tags: string[]; profile: string };
  profiles: { name: string; label: string; left_out_label: string }[];
  /** This PC (config.toml); port and data_dir apply after a restart. */
  machine: {
    config_path: string | null;
    anki_url: string;
    soffice: string;
    soffice_found: string | null;
    port: number;
    data_dir: string;
  };
};

export type SettingsPatch = Partial<{
  default_model: string;
  default_deck: string;
  default_tags: string[];
  default_profile: string;
  anki_url: string;
  soffice: string;
  port: number;
  data_dir: string;
}>;

export type GenerateBody = {
  mode: "selection" | "document";
  selection?: Pick<Source, "page" | "text" | "rects">;
  source_id?: string; // generate from this figure source, with the selection's text
  focus?: string;
  model?: string;
};

/** One undoable change to a document's cards, newest first in the history. */
export type HistoryEntry = { id: number; label: string; created_at: string; undone: boolean; cards: number };
/** label: what was undone or redone (null: nothing to do); message: e.g. cards still in Anki. */
export type StepResult = { label: string | null; message: string | null };

/** index: clanki's snapshot of the Anki collection, used for duplicate warnings. */
export type AnkiIndexSummary = { notes: number; refreshed_at: string | null };
export type AnkiStatus = { connected: boolean; version: number | null; problems: string[]; index: AnkiIndexSummary };

export type SendResult = {
  note_id: string;
  action: "added" | "updated" | "skipped" | "failed";
  anki_note_id: number | null;
  error: string | null;
};
export type SendResponse = { results: SendResult[]; summary: Record<SendResult["action"], number> };

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(method: string, url: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { "Content-Type": "application/json" };
  }
  const r = await fetch(url, init);
  if (!r.ok) throw await failure(r);
  return r.json() as Promise<T>;
}

async function failure(r: Response): Promise<ApiError> {
  let msg = r.statusText;
  try {
    const d = (await r.json()).detail;
    msg = typeof d === "string" ? d : JSON.stringify(d);
  } catch {
    /* not JSON */
  }
  return new ApiError(r.status, msg);
}

/** What to export: unsent is new and edited cards; tag matches the card's or its document's tags
 * (NHB matches NHB::vision); mark_exported makes Send skip them afterwards. */
export type ExportOptions = {
  document_ids: string[];
  scope: "unsent" | "all";
  types: ("qa" | "list")[];
  tag: string;
  mark_exported: boolean;
};

async function exportFile(o: ExportOptions): Promise<{ blob: Blob; name: string; cards: number }> {
  const r = await fetch("/api/export", { method: "POST", body: JSON.stringify(o), headers: { "Content-Type": "application/json" } });
  if (!r.ok) throw await failure(r);
  const name = /filename="([^"]+)"/.exec(r.headers.get("content-disposition") ?? "")?.[1] ?? "clanki_anki.txt";
  return { blob: await r.blob(), name, cards: Number(r.headers.get("x-clanki-cards") ?? 0) };
}

export const api = {
  documents: () => call<Doc[]>("GET", "/api/documents"),
  undo: (docId: string, to?: number) =>
    call<StepResult>("POST", `/api/documents/${docId}/undo${to === undefined ? "" : `?to=${to}`}`),
  redo: (docId: string, to?: number) =>
    call<StepResult>("POST", `/api/documents/${docId}/redo${to === undefined ? "" : `?to=${to}`}`),
  history: (docId: string) => call<HistoryEntry[]>("GET", `/api/documents/${docId}/history`),
  exportPreview: (o: ExportOptions) => call<{ cards: number; with_errors: number }>("POST", "/api/export", { ...o, preview: true }),
  exportFile,
  openUrl: (url: string) => call<Doc>("POST", "/api/documents/url", { url }),
  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return call<Doc>("POST", "/api/documents", fd);
  },
  updateDocument: (id: string, patch: Partial<Pick<Doc, "title" | "deck" | "tags">>) =>
    call<Doc>("PATCH", `/api/documents/${id}`, patch),
  deleteDocument: (id: string) => call<unknown>("DELETE", `/api/documents/${id}`),
  pdfUrl: (id: string) => `/api/documents/${id}/pdf`,

  sources: (docId: string) => call<Source[]>("GET", `/api/documents/${docId}/sources`),
  addSource: (docId: string, s: Pick<Source, "page" | "text" | "rects">) =>
    call<Source>("POST", `/api/documents/${docId}/sources`, s),

  notes: (docId: string) => call<Note[]>("GET", `/api/documents/${docId}/notes`),
  addNote: (docId: string, n: NoteDraft) => call<Note>("POST", `/api/documents/${docId}/notes`, n),
  updateNote: (id: string, patch: Partial<Note>) => call<Note>("PATCH", `/api/notes/${id}`, patch),
  deleteNote: (id: string) => call<Note>("DELETE", `/api/notes/${id}`),
  restoreNote: (id: string) => call<Note>("POST", `/api/notes/${id}/restore`),

  ankiStatus: () => call<AnkiStatus>("GET", "/api/anki/status"),
  ankiDecks: () => call<string[]>("GET", "/api/anki/decks"),
  transcribe: (docId: string, body: { page: number; rect: number[] | null; image: string }) =>
    call<{ job: Job; source: Source }>("POST", `/api/documents/${docId}/transcribe`, body),
  correctSource: (id: string, text: string) => call<Source>("PATCH", `/api/sources/${id}`, { text }),
  ankiRefresh: () => call<AnkiIndexSummary>("POST", "/api/anki/refresh"),
  send: (docId: string) => call<SendResponse>("POST", `/api/documents/${docId}/send`),

  generate: (docId: string, body: GenerateBody) =>
    call<{ jobs: Job[] }>("POST", `/api/documents/${docId}/generate`, body),
  estimate: (docId: string, model?: string) =>
    call<Estimate>("GET", `/api/documents/${docId}/estimate` + (model ? `?model=${encodeURIComponent(model)}` : "")),
  jobs: (docId: string) => call<Job[]>("GET", `/api/documents/${docId}/jobs`),
  cancelJob: (id: string) => call<Job>("POST", `/api/jobs/${id}/cancel`),
  retryJob: (id: string, model?: string) => call<Job>("POST", `/api/jobs/${id}/retry`, { model }),
  cardLeftOut: (id: string, index: number) => call<Job>("POST", `/api/jobs/${id}/left-out/${index}`),
  aiEdit: (noteId: string, instruction: string) => call<Job>("POST", `/api/notes/${noteId}/ai-edit`, { instruction }),
  acceptJob: (id: string) => call<{ job: Job; message: string | null }>("POST", `/api/jobs/${id}/accept`),
  discardJob: (id: string) => call<Job>("POST", `/api/jobs/${id}/discard`),

  settings: () => call<Settings>("GET", "/api/settings"),
  putSettings: (s: SettingsPatch) => call<Settings & { restart: boolean }>("PUT", "/api/settings", s),
  putKey: (provider: string, key: string) => call<KeyStatus>("PUT", `/api/settings/keys/${provider}`, { key }),
  deleteKey: (provider: string) => call<KeyStatus>("DELETE", `/api/settings/keys/${provider}`),
  testKey: (provider: string) =>
    call<{ ok: boolean; error: string | null }>("POST", `/api/settings/keys/${provider}/test`),
};
