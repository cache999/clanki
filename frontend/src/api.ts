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
  status: "new" | "sent" | "edited";
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
  deck: string;
  tags: string[];
};

/** A highlight, or a page range used for whole-document generation (kind "chunk", no rects).
 * rects are [x, y, w, h] as fractions of the page box. */
export type Source = {
  id: string;
  document_id: string;
  kind: "highlight" | "chunk";
  page: number;
  page_end: number | null;
  text: string;
  rects: number[][];
};

export type Job = {
  id: string;
  document_id: string;
  source_id: string | null;
  mode: "highlight" | "chunk";
  pages: [number, number];
  target: string;
  focus: string;
  model: string;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  error: string | null;
  attempts: number;
  usage: { cache_hit: number; cache_miss: number; output: number; reasoning: number };
  cost_usd: number;
  note_ids: string[];
  left_out: { text: string; reason: string }[];
  flags: string[];
  image_occlusion: string[];
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

export type KeyStatus = { set: boolean; source: "env" | "keyring" | null; hint: string | null };
export type Settings = {
  providers: { deepseek: { models: string[]; key: KeyStatus } };
  default_model: string;
};

export type GenerateBody = {
  mode: "selection" | "document";
  selection?: Pick<Source, "page" | "text" | "rects">;
  focus?: string;
  model?: string;
};

export type AnkiStatus = { connected: boolean; version: number | null; problems: string[] };

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
  if (!r.ok) {
    let msg = r.statusText;
    try {
      const d = (await r.json()).detail;
      msg = typeof d === "string" ? d : JSON.stringify(d);
    } catch {
      /* not JSON */
    }
    throw new ApiError(r.status, msg);
  }
  return r.json() as Promise<T>;
}

export const api = {
  documents: () => call<Doc[]>("GET", "/api/documents"),
  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return call<Doc>("POST", "/api/documents", fd);
  },
  updateDocument: (id: string, patch: Partial<Pick<Doc, "title" | "deck" | "tags">>) =>
    call<Doc>("PATCH", `/api/documents/${id}`, patch),
  deleteDocument: (id: string) => call<unknown>("DELETE", `/api/documents/${id}`),
  pdfUrl: (id: string) => `/api/documents/${id}/pdf`,
  exportUrl: (id: string, scope: "all" | "unsent" = "all") => `/api/documents/${id}/export.txt?scope=${scope}`,

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
  send: (docId: string) => call<SendResponse>("POST", `/api/documents/${docId}/send`),

  generate: (docId: string, body: GenerateBody) =>
    call<{ jobs: Job[] }>("POST", `/api/documents/${docId}/generate`, body),
  estimate: (docId: string, model?: string) =>
    call<Estimate>("GET", `/api/documents/${docId}/estimate` + (model ? `?model=${encodeURIComponent(model)}` : "")),
  jobs: (docId: string) => call<Job[]>("GET", `/api/documents/${docId}/jobs`),
  cancelJob: (id: string) => call<Job>("POST", `/api/jobs/${id}/cancel`),
  retryJob: (id: string, model?: string) => call<Job>("POST", `/api/jobs/${id}/retry`, { model }),
  cardLeftOut: (id: string, index: number) => call<Job>("POST", `/api/jobs/${id}/left-out/${index}`),

  settings: () => call<Settings>("GET", "/api/settings"),
  putSettings: (s: { default_model: string }) => call<Settings>("PUT", "/api/settings", s),
  putKey: (provider: string, key: string) => call<KeyStatus>("PUT", `/api/settings/keys/${provider}`, { key }),
  deleteKey: (provider: string) => call<KeyStatus>("DELETE", `/api/settings/keys/${provider}`),
  testKey: (provider: string) =>
    call<{ ok: boolean; error: string | null }>("POST", `/api/settings/keys/${provider}/test`),
};
