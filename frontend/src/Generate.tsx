// Generation UI: focus box, whole-document confirmation, jobs panel, settings dialog.
import { useEffect, useRef, useState } from "react";
import {
  api,
  type AnkiIndexSummary,
  type AnkiStatus,
  type Doc,
  type Estimate,
  type ExportOptions,
  type HistoryEntry,
  type Job,
  type Settings,
  type SettingsPatch,
} from "./api";
import { parseTags } from "./text";
import { jobSummary, money, pagesLabel } from "./jobs";

const MODE_LABELS: Record<string, string> = { edit: "edit", figure: "figure", transcribe: "read image" };

/** The model's transcription of a figure, for correcting. Ctrl+Enter makes it the selection (then
 * G / N / L as for selected text); Esc closes. */
export function SnippetBox(p: { label: string; text: string; onUse(text: string): void; onCancel(): void }) {
  const [v, setV] = useState(p.text);
  return (
    <div className="snippet">
      <span>
        {p.label}: correct it if needed, then <kbd>Ctrl+Enter</kbd> to card it · <kbd>Esc</kbd> closes
      </span>
      <textarea
        autoFocus
        rows={Math.min(12, Math.max(3, v.split("\n").length + 1))}
        value={v}
        onChange={(e) => setV(e.target.value)}
        onKeyDown={(e) => {
          e.stopPropagation();
          if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && v.trim()) p.onUse(v.trim());
          if (e.key === "Escape") p.onCancel();
        }}
      />
    </div>
  );
}

/** One-line focus prompt shown in the reader bar after G. Enter generates, Esc cancels. */
export function FocusBox(p: { pageLabel: string; onSubmit(focus: string): void; onCancel(): void }) {
  const [v, setV] = useState("");
  return (
    <span className="focusbox">
      Generate from {p.pageLabel} — focus:
      <input
        autoFocus
        value={v}
        placeholder="optional, e.g. MoA (Enter to generate, Esc to cancel)"
        onChange={(e) => setV(e.target.value)}
        onKeyDown={(e) => {
          e.stopPropagation();
          if (e.key === "Enter") p.onSubmit(v);
          if (e.key === "Escape") p.onCancel();
        }}
      />
    </span>
  );
}

export function DocumentConfirm(p: { estimate: Estimate; onSubmit(focus: string): void; onCancel(): void }) {
  const [focus, setFocus] = useState("");
  const e = p.estimate;
  return (
    <div className="overlay" onClick={p.onCancel}>
      <div className="dialog" role="dialog" aria-label="Generate whole document" onClick={(ev) => ev.stopPropagation()}>
        <h2>Generate cards for the whole document?</h2>
        <p>
          {e.chunks} section{e.chunks === 1 ? "" : "s"}, run in parallel · ≈{Math.round(e.input_tokens / 1000)}k input tokens
          (mostly cached) · ≈{Math.round(e.output_tokens / 1000)}k output · <b>≈ {money(e.cost_usd)}</b> with {e.model}
          {e.peak ? " (peak-hour price)" : " (off-peak price)"}
        </p>
        <label>
          Focus (optional)
          <input
            autoFocus
            value={focus}
            placeholder="e.g. drugs only"
            onChange={(ev) => setFocus(ev.target.value)}
            onKeyDown={(ev) => {
              ev.stopPropagation();
              if (ev.key === "Enter") p.onSubmit(focus);
              if (ev.key === "Escape") p.onCancel();
            }}
          />
        </label>
        <div className="dialog-actions">
          <button onClick={() => p.onSubmit(focus)}>Generate</button> <span className="muted">Enter</span>
          <button onClick={p.onCancel}>Cancel</button> <span className="muted">Esc</span>
        </div>
      </div>
    </div>
  );
}

function duration(j: Job, now: number): string {
  if (!j.started_at) return "";
  const end = j.finished_at ? Date.parse(j.finished_at) : now;
  return `${Math.max(0, Math.round((end - Date.parse(j.started_at)) / 1000))}s`;
}

export function JobsPanel(p: {
  jobs: Job[];
  onClose(): void;
  onChanged(): void;
  onShowSource(sourceId: string): void;
  say(text: string, kind?: "info" | "error"): void;
}) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const s = jobSummary(p.jobs);
  const act = async (f: () => Promise<unknown>) => {
    try {
      await f();
      p.onChanged();
    } catch (e) {
      p.say(e instanceof Error ? e.message : String(e), "error");
    }
  };
  return (
    <div className="jobs-panel" role="dialog" aria-label="Generation jobs">
      <div className="jobs-head">
        <b>Jobs</b>
        <span className="muted">
          {s.active} running · {s.failed} failed · {money(s.cost)} for this document
        </span>
        <span className="spacer" />
        <button onClick={p.onClose} title="Close (Esc or .)">
          ×
        </button>
      </div>
      {!p.jobs.length && <p className="muted pad">No jobs yet. Select text and press G.</p>}
      {p.jobs.map((j) => (
        <div key={j.id} className={`job st-${j.status}`}>
          <div className="job-line">
            <span className={`dot ${j.status}`} title={j.status} />
            <button className="chip" onClick={() => j.source_id && p.onShowSource(j.source_id)}>
              {pagesLabel(j.pages)}
            </button>
            {j.focus && <span className="focus">“{j.focus.length > 30 ? j.focus.slice(0, 30) + "…" : j.focus}”</span>}
            <span className="muted">{j.model.replace("deepseek-", "")}</span>
            <span className="muted">{j.status}</span>
            <span className="muted">{duration(j, now)}</span>
            {j.mode !== "highlight" && j.mode !== "chunk" && <span className="muted">{MODE_LABELS[j.mode]}</span>}
            {j.status === "done" && <span>{j.mode === "edit" ? "suggestion ready" : j.mode === "transcribe" ? "text ready" : `${j.note_ids.length} cards`}</span>}
            <span className="muted">{money(j.cost_usd)}</span>
            <span className="spacer" />
            {(j.status === "queued" || j.status === "running") && (
              <button onClick={() => act(() => api.cancelJob(j.id))}>Cancel</button>
            )}
            {(j.status === "failed" || j.status === "cancelled" || j.status === "done") && (
              <button onClick={() => act(() => api.retryJob(j.id))} title="Run this job again">
                Retry
              </button>
            )}
          </div>
          {j.error && <div className="job-error">{j.error}</div>}
          {j.flags.map((f, i) => (
            <div key={i} className="job-flag">
              ⚠ {f}
            </div>
          ))}
          {j.left_out.length > 0 && (
            <details className="left-out">
              <summary>{j.left_out.length} left out (UKMLA scope)</summary>
              <ul>
                {j.left_out.map((x, i) => (
                  <li key={i}>
                    {x.text} <span className="muted">— {x.reason}</span>{" "}
                    <button onClick={() => act(() => api.cardLeftOut(j.id, i))}>Card this</button>
                  </li>
                ))}
              </ul>
            </details>
          )}
          {j.image_occlusion.length > 0 && (
            <div className="muted small">Image occlusion candidates: {j.image_occlusion.join("; ")}</div>
          )}
        </div>
      ))}
    </div>
  );
}

/** Export filters, with a live count. Enter exports, Esc closes. */
export function ExportDialog(p: {
  doc: Doc;
  allDocIds: string[];
  onDone(r: { cards: number; name: string; marked: boolean }): void;
  onClose(): void;
}) {
  const [scope, setScope] = useState<ExportOptions["scope"]>("unsent");
  const [qa, setQa] = useState(true);
  const [lists, setLists] = useState(true);
  const [tag, setTag] = useState("");
  const [all, setAll] = useState(false);
  const [mark, setMark] = useState(true);
  const [count, setCount] = useState<{ cards: number; with_errors: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const opts: ExportOptions = {
    document_ids: all ? p.allDocIds : [p.doc.id],
    scope,
    types: [...(qa ? ["qa" as const] : []), ...(lists ? ["list" as const] : [])],
    tag,
    mark_exported: mark,
  };
  const key = JSON.stringify(opts);
  useEffect(() => {
    void api.exportPreview(opts).then(setCount, () => setCount(null));
  }, [key]);
  async function go() {
    if (!count?.cards) return;
    try {
      const r = await api.exportFile(opts);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(r.blob);
      a.download = r.name;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 10_000); // revoking at once can cancel the download
      p.onDone({ cards: r.cards, name: r.name, marked: mark });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  return (
    <div className="overlay" onClick={p.onClose}>
      <div
        className="dialog export"
        role="dialog"
        aria-label="Export"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          e.stopPropagation();
          if (e.key === "Escape") p.onClose();
          if (e.key === "Enter" && (e.target as HTMLElement).tagName !== "BUTTON") void go();
        }}
      >
        <h2>Export an Anki import file</h2>
        <div className="row">
          <label className="choice">
            <input type="radio" checked={scope === "unsent"} onChange={() => setScope("unsent")} autoFocus /> New and edited
          </label>
          <label className="choice">
            <input type="radio" checked={scope === "all"} onChange={() => setScope("all")} /> All cards
          </label>
        </div>
        <div className="row">
          <label className="choice">
            <input type="checkbox" checked={qa} onChange={(e) => setQa(e.target.checked)} /> Q/A cards
          </label>
          <label className="choice">
            <input type="checkbox" checked={lists} onChange={(e) => setLists(e.target.checked)} /> Lists
          </label>
          <input value={tag} placeholder="only this tag (e.g. NHB)" onChange={(e) => setTag(e.target.value)} />
        </div>
        <div className="row">
          <label className="choice">
            <input type="radio" checked={!all} onChange={() => setAll(false)} /> {p.doc.title}
          </label>
          <label className="choice">
            <input type="radio" checked={all} onChange={() => setAll(true)} /> All documents ({p.allDocIds.length})
          </label>
        </div>
        <label className="choice">
          <input type="checkbox" checked={mark} onChange={(e) => setMark(e.target.checked)} /> Mark them exported, so Send
          to Anki skips them (import the file in Anki: File ▸ Import)
        </label>
        <p className="export-count">
          {count ? `${count.cards} card${count.cards === 1 ? "" : "s"}` : "…"}
          {count?.with_errors ? ` · ${count.with_errors} with errors left out (fix them first)` : ""}
        </p>
        {error && <p className="bad">{error}</p>}
        <div className="dialog-actions">
          <button disabled={!count?.cards} onClick={() => void go()}>
            Export
          </button>
          <button onClick={p.onClose}>Cancel</button> <span className="muted">Enter · Esc</span>
        </div>
      </div>
    </div>
  );
}

/** The document's undo history, newest first. Clicking a change undoes back to it (or, if it is
 * undone, redoes up to it). `version` changes whenever the cards do, to reload the list. */
export function HistoryPanel(p: { docId: string; version: unknown; onPick(e: HistoryEntry): void; onClose(): void }) {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  useEffect(() => {
    void api.history(p.docId).then(setEntries, () => setEntries([]));
  }, [p.docId, p.version]);
  return (
    <div className="jobs-panel history" role="dialog" aria-label="Undo history">
      <div className="jobs-head">
        <b>History</b>
        <span className="muted">click a change to undo back to it · Z undo · Shift+Z redo</span>
        <span className="spacer" />
        <button onClick={p.onClose} title="Close (Esc or H)">
          ×
        </button>
      </div>
      {!entries.length && <p className="muted">No changes yet.</p>}
      <ul>
        {entries.map((e) => (
          <li key={e.id} className={e.undone ? "undone" : ""} onClick={() => p.onPick(e)} title={e.undone ? "Redo up to here" : "Undo back to here"}>
            <span>{e.label}</span>
            <span className="muted">{new Date(e.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Defaults(p: { settings: Settings; onSave(patch: SettingsPatch): void }) {
  const d = p.settings.defaults;
  const [deck, setDeck] = useState(d.deck);
  const [tags, setTags] = useState(d.tags.join(" "));
  const [profile, setProfile] = useState(d.profile);
  return (
    <div className="defaults section">
      <h3>For new documents</h3>
      <div className="row">
        <label>
          Deck
          <input value={deck} list="decks" onChange={(e) => setDeck(e.target.value)} />
        </label>
        <label>
          Tags
          <input value={tags} placeholder="space-separated" onChange={(e) => setTags(e.target.value)} />
        </label>
        <label>
          Profile
          <select value={profile} onChange={(e) => setProfile(e.target.value)}>
            {p.settings.profiles.map((x) => (
              <option key={x.name} value={x.name}>
                {x.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div>
        <button onClick={() => p.onSave({ default_deck: deck.trim(), default_tags: parseTags(tags), default_profile: profile })}>
          Save defaults
        </button>
      </div>
    </div>
  );
}

function Machine(p: { settings: Settings; onSave(patch: SettingsPatch): void }) {
  const m = p.settings.machine;
  const [anki, setAnki] = useState(m.anki_url);
  const [soffice, setSoffice] = useState(m.soffice);
  const [port, setPort] = useState(String(m.port));
  const [dataDir, setDataDir] = useState(m.data_dir);
  const editable = m.config_path !== null;
  return (
    <div className="machine section">
      <h3>This computer</h3>
      <div className="row">
        <label>
          Anki address (AnkiConnect)
          <input value={anki} disabled={!editable} onChange={(e) => setAnki(e.target.value)} />
        </label>
        <label>
          Port
          <input value={port} disabled={!editable} inputMode="numeric" onChange={(e) => setPort(e.target.value)} />
        </label>
      </div>
      <label>
        LibreOffice program (for PPTX and DOCX; empty finds it)
        <input value={soffice} disabled={!editable} placeholder={m.soffice_found ?? "not found"} onChange={(e) => setSoffice(e.target.value)} />
      </label>
      <p className="muted small">{m.soffice_found ? `Using ${m.soffice_found}` : "LibreOffice not found: PPTX and DOCX can't be opened."}</p>
      <label>
        Data folder (documents and cards; e.g. a OneDrive folder, used by one PC at a time)
        <input value={dataDir} disabled={!editable} onChange={(e) => setDataDir(e.target.value)} />
      </label>
      {editable ? (
        <div>
          <button onClick={() => p.onSave({ anki_url: anki.trim(), soffice: soffice.trim(), port: Number(port), data_dir: dataDir.trim() })}>
            Save for this computer
          </button>{" "}
          <span className="muted small">in {m.config_path}; port and data folder apply after a restart</span>
        </div>
      ) : (
        <p className="muted small">clanki was started without a config file, so these can't be changed here.</p>
      )}
    </div>
  );
}

/** What clanki knows of the Anki collection, for duplicate warnings. */
export function indexLine(index: AnkiIndexSummary | undefined): string {
  if (!index?.refreshed_at) return "clanki has not read your Anki cards yet: duplicate warnings start once Anki is open.";
  const when = new Date(index.refreshed_at).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  return `${index.notes.toLocaleString()} cards read from Anki (${when}): new cards are checked against them.`;
}

export function SettingsDialog(p: {
  settings: Settings;
  anki: AnkiStatus | null;
  onChange(s: Settings): void;
  onAnkiRead(status: AnkiStatus): void;
  onClose(): void;
}) {
  const ds = p.settings.providers.deepseek;
  const [key, setKey] = useState("");
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const run = async <T,>(f: () => Promise<T>, ok: string | ((r: T) => string)) => {
    try {
      const r = await f();
      p.onChange(await api.settings());
      setMsg({ text: typeof ok === "string" ? ok : ok(r), ok: true });
    } catch (e) {
      setMsg({ text: e instanceof Error ? e.message : String(e), ok: false });
    }
  };
  const status = !ds.key.set
    ? "not set"
    : ds.key.source === "env"
      ? `set from the DEEPSEEK_API_KEY environment variable (${ds.key.hint})`
      : `stored in this computer's credential store (${ds.key.hint})`;
  return (
    <div className="overlay" onClick={p.onClose}>
      <div
        className="dialog"
        role="dialog"
        aria-label="Settings"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          e.stopPropagation();
          if (e.key === "Escape") p.onClose();
        }}
      >
        <h2>Settings</h2>
        <h3>DeepSeek API key</h3>
        <p className="key-status">Key: {status}</p>
        {!ds.key.store ? (
          <p className="muted small">
            This system has no credential store (WSL), so set the DEEPSEEK_API_KEY environment variable and restart clanki
            (see the README).
          </p>
        ) : (
        <div className="row">
          <input
            ref={input}
            autoFocus
            type="password"
            autoComplete="off"
            value={key}
            placeholder="paste a new key (sk-…)"
            onChange={(e) => setKey(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && key.trim()) void run(() => api.putKey("deepseek", key), "Key saved");
            }}
          />
          <button disabled={!key.trim()} onClick={() => run(() => api.putKey("deepseek", key).then(() => setKey("")), "Key saved")}>
            Save
          </button>
          <button disabled={!ds.key.set} onClick={() => run(() => api.testKey("deepseek").then((r) => {
            if (!r.ok) throw new Error(r.error ?? "test failed");
          }), "The key works")}>
            Test
          </button>
          <button
            disabled={!ds.key.set || ds.key.source === "env"}
            onClick={() => run(() => api.deleteKey("deepseek"), "Key removed")}
          >
            Remove
          </button>
        </div>
        )}
        {msg && <p className={msg.ok ? "ok" : "bad"}>{msg.text}</p>}
        <p className="muted small">
          Keys are kept in Windows Credential Manager (never in clanki's files). An environment variable takes
          precedence.
        </p>
        <h3>Model for generation</h3>
        <select
          value={p.settings.default_model}
          onChange={(e) => run(() => api.putSettings({ default_model: e.target.value }), "Model saved")}
        >
          {ds.models.map((m) => (
            <option key={m}>{m}</option>
          ))}
        </select>
        <p className="muted small">deepseek-flash is cheapest; deepseek-v4-pro is stronger and about 4× the price.</p>
        <Defaults settings={p.settings} onSave={(patch) => run(() => api.putSettings(patch), "Defaults saved")} />
        <Machine
          settings={p.settings}
          onSave={(patch) =>
            run(
              () => api.putSettings(patch),
              (r) => (r.restart ? "Saved: restart clanki for the new port or data folder to take effect" : "Saved"),
            )
          }
        />
        <h3>Anki</h3>
        <p>{indexLine(p.anki?.index)}</p>
        <div className="row">
          <button
            onClick={() =>
              run(async () => {
                await api.ankiRefresh();
                p.onAnkiRead(await api.ankiStatus());
              }, "Read your Anki cards")
            }
          >
            Re-read Anki
          </button>
        </div>
        <h3>Subquestion vocabulary</h3>
        <p className="facets small">{p.settings.facets.join(", ")}</p>
        <p className="muted small">
          The model is asked to use these in brackets, e.g. “Sacubitril (MoA, use)”: clanki’s list, then the ones you
          use most in Anki.
        </p>
        <div className="dialog-actions">
          <button onClick={p.onClose}>Close</button> <span className="muted">Esc</span>
        </div>
      </div>
    </div>
  );
}
