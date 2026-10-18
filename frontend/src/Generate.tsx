// Generation UI: focus box, whole-document confirmation, jobs panel, settings dialog.
import { useEffect, useRef, useState } from "react";
import { api, type AnkiIndexSummary, type AnkiStatus, type Estimate, type Job, type Settings } from "./api";
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
  const run = async (f: () => Promise<unknown>, ok: string) => {
    try {
      await f();
      p.onChange(await api.settings());
      setMsg({ text: ok, ok: true });
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
