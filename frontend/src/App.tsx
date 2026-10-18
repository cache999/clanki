import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type AnkiStatus, type Doc, type Estimate, type Job, type Note, type NoteDraft, type Settings, type Source } from "./api";
import { Cards, type EditTarget } from "./Cards";
import { sourceLabel } from "./figure";
import { DocumentConfirm, ExportDialog, FocusBox, HistoryPanel, indexLine, JobsPanel, SettingsDialog, SnippetBox } from "./Generate";
import { Help } from "./Help";
import { jobSummary, money, openEdits, sourceStates } from "./jobs";
import { commandFor, isTyping, type Command } from "./keys";
import { Reader, type ReaderHandle, type ReaderSelection, type Region } from "./Reader";
import { joinLines, orderNotes, splitItems } from "./selection";
import { parseTags } from "./text";

type Toast = { text: string; kind: "info" | "error" };

const LAST_DOC = "clanki.lastDoc";
const remember = (id: string) => {
  try {
    localStorage.setItem(LAST_DOC, id);
  } catch {
    /* storage unavailable */
  }
};
const recall = () => {
  try {
    return localStorage.getItem(LAST_DOC);
  } catch {
    return null;
  }
};

export function App() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [docId, setDocId] = useState<string | null>(null);
  const [notes, setNotes] = useState<Note[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editing, setEditing] = useState<EditTarget | null>(null);
  const [draft, setDraft] = useState<(NoteDraft & { sel?: ReaderSelection }) | null>(null);
  const [selection, setSelection] = useState<ReaderSelection | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [anki, setAnki] = useState<AnkiStatus | null>(null);
  const [sendErrors, setSendErrors] = useState<Record<string, string>>({});
  const [toast, setToast] = useState<Toast | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [help, setHelp] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [focusOpen, setFocusOpen] = useState(false);
  const [docConfirm, setDocConfirm] = useState<Estimate | null>(null);
  const [jobsOpen, setJobsOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [askingFor, setAskingFor] = useState<string | null>(null);
  // figures: drawing a box, waiting for the model's transcription, then correcting it
  const [regionMode, setRegionMode] = useState(false);
  const [awaiting, setAwaiting] = useState<string | null>(null); // source id being transcribed
  const [snippet, setSnippet] = useState<Source | null>(null);
  const reader = useRef<ReaderHandle>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const doc = docs.find((d) => d.id === docId) ?? null;
  const ordered = useMemo(() => orderNotes(notes, sources), [notes, sources]);
  const sourceLabels = useMemo(
    () => new Map(sources.map((s) => [s.id, sourceLabel(s)])),
    [sources],
  );
  const sourceStatus = useMemo(() => sourceStates(jobs), [jobs]);
  const edits = useMemo(() => openEdits(jobs), [jobs]);
  const summary = jobSummary(jobs);
  const sourcesWithCards = useMemo(() => new Set(notes.map((n) => n.source_id).filter(Boolean) as string[]), [notes]);
  const selected = notes.find((n) => n.id === selectedId) ?? null;

  const say = useCallback((text: string, kind: Toast["kind"] = "info") => {
    setToast({ text, kind });
  }, []);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), toast.kind === "error" ? 8000 : 4000);
    return () => clearTimeout(t);
  }, [toast]);

  async function guard<T>(p: Promise<T>): Promise<T | undefined> {
    try {
      return await p;
    } catch (e) {
      say(e instanceof Error ? e.message : String(e), "error");
      return undefined;
    }
  }

  const refresh = useCallback(async (id: string) => {
    const [n, s] = await Promise.all([api.notes(id), api.sources(id)]);
    setNotes(n);
    setSources(s);
  }, []);

  useEffect(() => {
    void guard(api.documents()).then((d) => {
      if (!d) return;
      setDocs(d);
      const last = recall();
      setDocId(d.some((x) => x.id === last) ? last : (d[d.length - 1]?.id ?? null));
    });
    void api.settings().then(setSettings, () => setSettings(null));
    const poll = () => void api.ankiStatus().then(setAnki, () => setAnki(null));
    poll();
    const t = setInterval(poll, 15000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    setNotes([]);
    setSources([]);
    setSelectedId(null);
    setEditing(null);
    setDraft(null);
    setSelection(null);
    setHistoryOpen(false);
    setSendErrors({});
    setJobs([]);
    setFocusOpen(false);
    setRegionMode(false);
    setAwaiting(null);
    setSnippet(null);
    if (docId) {
      remember(docId);
      void guard(refresh(docId));
      void guard(api.jobs(docId)).then((j) => j && setJobs(j));
    }
  }, [docId]);

  // While jobs run, poll once a second; when one finishes, reload the cards it made.
  const activeIds = jobs.filter((j) => j.status === "queued" || j.status === "running").map((j) => j.id).join(",");
  useEffect(() => {
    if (!docId || !activeIds) return;
    const t = setInterval(async () => {
      const latest = await api.jobs(docId).catch(() => null);
      if (!latest) return;
      setJobs(latest);
      const stillActive = new Set(latest.filter((j) => j.status === "queued" || j.status === "running").map((j) => j.id));
      if (activeIds.split(",").some((id) => !stillActive.has(id))) {
        await refresh(docId);
        const failed = latest.filter((j) => activeIds.includes(j.id) && j.status === "failed");
        const what = { edit: "AI edit", transcribe: "Reading the image" }[failed[0]?.mode as string] ?? "Generation";
        if (failed.length) say(`${what} failed: ${failed[0].error}`, "error");
      }
    }, 1000);
    return () => clearInterval(t);
  }, [docId, activeIds]);

  async function reloadJobs() {
    if (!docId) return;
    const j = await guard(api.jobs(docId));
    if (j) setJobs(j);
    await refresh(docId);
  }

  async function generateSelection(focus: string) {
    if (!doc || !selection) return;
    setFocusOpen(false);
    const r = await guard(
      api.generate(doc.id, {
        mode: "selection",
        selection: { page: selection.page, text: selection.text, rects: selection.rects },
        source_id: selection.sourceId,
        focus,
      }),
    );
    if (!r) return;
    setSelection(null);
    reader.current?.clearSelection();
    await reloadJobs();
  }

  async function confirmDocument() {
    if (!doc) return;
    const e = await guard(api.estimate(doc.id));
    if (e) setDocConfirm(e);
  }

  async function generateDocument(focus: string) {
    if (!doc) return;
    setDocConfirm(null);
    const r = await guard(api.generate(doc.id, { mode: "document", focus }));
    if (!r) return;
    say(`Generating ${r.jobs.length} section${r.jobs.length === 1 ? "" : "s"}… (. shows progress)`);
    await reloadJobs();
  }

  async function askEdit(noteId: string, instruction: string) {
    setAskingFor(null);
    if (await guard(api.aiEdit(noteId, instruction))) await reloadJobs();
  }

  async function accept(job: Job) {
    const r = await guard(api.acceptJob(job.id));
    if (!r) return reloadJobs();
    if (r.message) say(r.message);
    await reloadJobs();
    if (r.job.note_ids[0]) setSelectedId(r.job.note_ids[0]);
  }

  async function discard(job: Job) {
    if (await guard(api.discardJob(job.id))) await reloadJobs();
  }

  async function transcribe(page: number, rect: number[] | null, image: string) {
    if (!doc) return say("Open a document first (O)");
    const r = await guard(api.transcribe(doc.id, { page, rect, image }));
    if (!r) return;
    setAwaiting(r.source.id);
    setSelection(null);
    say("Reading the image…");
    await refresh(doc.id);
    await reloadJobs();
  }

  // when the transcription arrives, open it for correcting
  useEffect(() => {
    if (!awaiting) return;
    const j = jobs.find((x) => x.source_id === awaiting && x.mode === "transcribe");
    const s = sources.find((x) => x.id === awaiting);
    if (j && ["failed", "cancelled"].includes(j.status)) setAwaiting(null);
    else if (j?.status === "done" && s?.text) {
      setAwaiting(null);
      setSnippet(s);
    }
  }, [awaiting, jobs, sources]);

  async function cardSnippet(text: string) {
    const s = snippet;
    if (!s) return;
    setSnippet(null);
    if (text !== s.text && !(await guard(api.correctSource(s.id, text)))) return;
    if (doc) await refresh(doc.id);
    setSelection({ page: s.page, text, rects: s.rects, sourceId: s.id });
  }

  // a pasted screenshot is read like a figure on the page being read
  const pasteRef = useRef<(e: ClipboardEvent) => void>(() => {});
  pasteRef.current = (e: ClipboardEvent) => {
    if (isTyping(e.target)) return;
    const file = [...(e.clipboardData?.files ?? [])].find((f) => f.type.startsWith("image/"));
    if (!file) return;
    e.preventDefault();
    const fr = new FileReader();
    fr.onload = () => void transcribe(reader.current?.currentPage() ?? 1, null, String(fr.result));
    fr.readAsDataURL(file);
  };
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => pasteRef.current(e);
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, []);

  async function changeModel(model: string) {
    const s = await guard(api.putSettings({ default_model: model }));
    if (s) setSettings(s);
  }

  async function openFile(file: File) {
    setBusy(`Opening ${file.name}…`);
    const d = await guard(api.upload(file));
    setBusy(null);
    if (!d) return;
    setDocs((xs) => [...xs, d]);
    setDocId(d.id);
  }

  async function openUrl() {
    const url = window.prompt("Web page address (its article and figures open as a document):")?.trim();
    if (!url) return;
    setBusy("Opening the web page…");
    const d = await guard(api.openUrl(url.includes("://") ? url : "https://" + url));
    setBusy(null);
    if (!d) return;
    setDocs((xs) => [...xs, d]);
    setDocId(d.id);
  }

  async function updateDoc(patch: Partial<Pick<Doc, "deck" | "tags" | "title">>) {
    if (!doc) return;
    const d = await guard(api.updateDocument(doc.id, patch));
    if (d) setDocs((xs) => xs.map((x) => (x.id === d.id ? d : x)));
  }

  async function deleteDoc() {
    if (!doc || !confirm(`Remove “${doc.title}” and its ${notes.length} cards from clanki? Cards already in Anki stay there.`))
      return;
    await guard(api.deleteDocument(doc.id));
    const rest = docs.filter((d) => d.id !== doc.id);
    setDocs(rest);
    setDocId(rest[rest.length - 1]?.id ?? null);
  }

  function startNew(type: Note["type"]) {
    if (!doc) return say("Open a document first (O)");
    const sel = selection ?? undefined;
    const base: NoteDraft =
      type === "qa" ? { type, back: sel ? joinLines(sel.text) : "" } : { type, items: sel ? splitItems(sel.text) : [] };
    setDraft({ ...base, sel });
    setEditing({ id: "draft" });
  }

  async function create(fields: NoteDraft & { sel?: ReaderSelection }) {
    if (!doc) return;
    const { sel, ...note } = fields;
    let source_id: string | null = sel?.sourceId ?? null;
    if (sel && !sel.sourceId) {
      const s = await guard(api.addSource(doc.id, { page: sel.page, text: sel.text, rects: sel.rects }));
      if (!s) return;
      source_id = s.id;
    }
    const n = await guard(api.addNote(doc.id, { ...note, source_id }));
    if (!n) return;
    setDraft(null);
    setEditing(null);
    setSelection(null);
    reader.current?.clearSelection();
    await refresh(doc.id);
    setSelectedId(n.id);
  }

  async function save(id: string, fields: Partial<Note>) {
    if (!doc) return;
    if (await guard(api.updateNote(id, fields))) {
      setEditing(null);
      setSendErrors(({ [id]: _, ...rest }) => rest);
      await refresh(doc.id);
    }
  }

  async function dismissFlag(id: string, flag: string) {
    const n = notes.find((x) => x.id === id);
    if (!doc || !n) return;
    if (await guard(api.updateNote(id, { flags: n.flags.filter((f) => f !== flag) }))) await refresh(doc.id);
  }

  function move(delta: number) {
    if (!ordered.length) return;
    const i = ordered.findIndex((n) => n.id === selectedId);
    const next = i < 0 ? (delta > 0 ? 0 : ordered.length - 1) : Math.min(Math.max(i + delta, 0), ordered.length - 1);
    setSelectedId(ordered[next].id);
    const s = ordered[next].source_id;
    if (s) reader.current?.showSource(s);
  }

  async function remove() {
    if (!doc || !selected) return;
    const i = ordered.findIndex((n) => n.id === selected.id);
    if (!(await guard(api.deleteNote(selected.id)))) return;
    const after = ordered[i + 1] ?? ordered[i - 1];
    setSelectedId(after?.id ?? null);
    await refresh(doc.id);
    say("Card deleted · Z to undo");
  }

  async function step(dir: "undo" | "redo", to?: number) {
    if (!doc) return;
    const r = await guard(dir === "undo" ? api.undo(doc.id, to) : api.redo(doc.id, to));
    if (!r) return;
    if (!r.label) return say(dir === "undo" ? "Nothing to undo" : "Nothing to redo");
    say(`${dir === "undo" ? "Undid" : "Redid"}: ${r.label}${r.message ? " · " + r.message : ""}`);
    await refresh(doc.id);
  }

  async function toggleReverse() {
    if (!selected || selected.type !== "qa") return;
    if (selected.add_reverse) await save(selected.id, { add_reverse: false });
    else setEditing({ id: selected.id, focus: "reverse_prompt", preset: { add_reverse: true } });
  }

  async function send() {
    if (!doc) return;
    setBusy("Sending to Anki…");
    const r = await guard(api.send(doc.id));
    setBusy(null);
    if (!r) return;
    const errors: Record<string, string> = {};
    for (const x of r.results) if (x.action === "failed" && x.error) errors[x.note_id] = x.error;
    setSendErrors(errors);
    const s = r.summary;
    say(
      `Anki: ${s.added} added, ${s.updated} updated, ${s.skipped} already up to date` +
        (s.failed ? `, ${s.failed} not sent (see cards)` : ""),
      s.failed ? "error" : "info",
    );
    await refresh(doc.id);
  }

  const run = (c: Command) => {
    const r = reader.current;
    switch (c) {
      case "newCard":
        return startNew("qa");
      case "newList":
        return startNew("list");
      case "generate":
        if (!doc) return say("Open a document first (O)");
        if (!selection) return say("Select text first, or press Shift+G for the whole document");
        return setFocusOpen(true);
      case "generateDocument":
        return doc ? void confirmDocument() : say("Open a document first (O)");
      case "figure":
        if (!doc) return say("Open a document first (O)");
        setSelection(null);
        reader.current?.clearSelection();
        return setRegionMode(true);
      case "jobs":
        return setJobsOpen((o) => !o);
      case "aiEdit":
        return selected ? setAskingFor(selected.id) : say("Select a card first (J/K)");
      case "acceptSuggestion": {
        const j = selected && edits.get(selected.id);
        return j && j.status === "done" ? void accept(j) : say("No AI suggestion on the selected card");
      }
      case "discardSuggestion": {
        const j = selected && edits.get(selected.id);
        return j && (j.status === "done" || j.status === "failed") ? void discard(j) : undefined;
      }
      case "settings":
        return setSettingsOpen(true);
      case "next":
        return move(1);
      case "prev":
        return move(-1);
      case "edit":
        return selected && setEditing({ id: selected.id });
      case "delete":
        return void remove();
      case "undo":
        return void step("undo");
      case "redo":
        return void step("redo");
      case "history":
        return doc ? setHistoryOpen((o) => !o) : say("Open a document first (O)");
      case "toggleReverse":
        return void toggleReverse();
      case "prevPage":
        return r?.prevPage();
      case "nextPage":
        return r?.nextPage();
      case "zoomIn":
        return r?.zoomIn();
      case "zoomOut":
        return r?.zoomOut();
      case "zoomFit":
        return r?.zoomFit();
      case "send":
        return void send();
      case "export":
        return doc ? setExportOpen(true) : say("Open a document first (O)");
      case "open":
        return fileInput.current?.click();
      case "openUrl":
        return void openUrl();
      case "help":
        return setHelp(true);
    }
  };
  const runRef = useRef(run);
  runRef.current = run;

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !isTyping(e.target)) {
        if (help) setHelp(false);
        else if (jobsOpen) setJobsOpen(false);
        else if (historyOpen) setHistoryOpen(false);
        else if (regionMode) setRegionMode(false);
        else if (selection) {
          setSelection(null);
          reader.current?.clearSelection();
        }
        return;
      }
      if (help || settingsOpen || docConfirm || exportOpen) return;
      const c = commandFor(e, isTyping(e.target) || editing !== null || focusOpen || askingFor !== null);
      if (c) {
        e.preventDefault();
        runRef.current(c);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [help, selection, editing, jobsOpen, settingsOpen, docConfirm, focusOpen, askingFor, regionMode, historyOpen, exportOpen]);

  const pending = notes.filter((n) => n.status === "new" || n.status === "edited").length;
  return (
    <div
      className="app"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        const f = e.dataTransfer.files[0];
        if (f) void openFile(f);
      }}
    >
      <header className="topbar">
        <b className="brand">clanki</b>
        <select value={docId ?? ""} onChange={(e) => setDocId(e.target.value || null)} title="Open documents">
          {!docs.length && <option value="">No documents</option>}
          {docs.map((d) => (
            <option key={d.id} value={d.id}>
              {d.title}
            </option>
          ))}
        </select>
        <button onClick={() => fileInput.current?.click()} title="Open a PDF, PPTX or DOCX (O)">
          Open…
        </button>
        <button onClick={() => void openUrl()} title="Open a web page by its address (Shift+O)">
          Web page…
        </button>
        <input
          ref={fileInput}
          type="file"
          accept=".pdf,.pptx,.ppt,.odp,.docx,.doc,.odt"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) void openFile(f);
          }}
        />
        {doc && (
          <>
            <DocField
              key={doc.id + "deck"}
              label="Deck"
              value={doc.deck}
              placeholder="Default"
              list="decks"
              onCommit={(deck) => updateDoc({ deck })}
            />
            <DocField
              key={doc.id + "tags"}
              label="Tags"
              value={doc.tags.join(" ")}
              placeholder="NHB::vision"
              onCommit={(t) => updateDoc({ tags: parseTags(t) })}
            />
            <button onClick={deleteDoc} title="Remove this document from clanki">
              Remove
            </button>
          </>
        )}
        <span className="spacer" />
        {busy && <span className="busy">{busy}</span>}
        {settings && (
          <select
            className="model"
            value={settings.default_model}
            onChange={(e) => changeModel(e.target.value)}
            title="Model for generation"
          >
            {settings.providers.deepseek.models.map((m) => (
              <option key={m}>{m}</option>
            ))}
          </select>
        )}
        <button
          className={`jobs-btn ${summary.active ? "active" : ""} ${summary.failed ? "has-failed" : ""}`}
          onClick={() => setJobsOpen((o) => !o)}
          title="Generation jobs (.)"
        >
          Jobs{summary.active ? ` ● ${summary.active}` : ""}
          {summary.failed ? ` ⚠ ${summary.failed}` : ""}
          {summary.cost ? ` · ${money(summary.cost)}` : ""}
        </button>
        <AnkiPill status={anki} />
        <button onClick={() => run("send")} disabled={!doc} title="Send new and edited cards to Anki (S)">
          Send to Anki{pending ? ` (${pending})` : ""}
        </button>
        <button onClick={() => run("export")} disabled={!doc} title="Download an Anki import file (Shift+E)">
          Export .txt
        </button>
        <button onClick={() => setSettingsOpen(true)} title="Settings (,)">
          ⚙
        </button>
        <button onClick={() => setHelp(true)} title="Keyboard shortcuts (?)">
          ?
        </button>
      </header>
      {settings && !settings.providers.deepseek.key.set && (
        <div className="banner">
          No DeepSeek API key yet: generation needs one.{" "}
          <button onClick={() => setSettingsOpen(true)}>Add it in Settings</button>
        </div>
      )}
      <DeckList connected={!!anki?.connected} />
      <main className="main">
        {doc ? (
          <Reader
            ref={reader}
            url={api.pdfUrl(doc.id)}
            sources={sources}
            activeSourceId={selected?.source_id ?? null}
            sourcesWithCards={sourcesWithCards}
            sourceStatus={sourceStatus}
            notes={notes}
            selection={selection}
            bar={
              focusOpen && selection ? (
                <FocusBox
                  pageLabel={selection.sourceId ? `the figure on p.${selection.page}` : `p.${selection.page}`}
                  onSubmit={(f) => void generateSelection(f)}
                  onCancel={() => setFocusOpen(false)}
                />
              ) : snippet ? (
                <SnippetBox
                  key={snippet.id}
                  label={`Read from the ${snippet.kind === "region" ? "figure" : "image"} on p.${snippet.page}`}
                  text={snippet.text}
                  onUse={(t) => void cardSnippet(t)}
                  onCancel={() => setSnippet(null)}
                />
              ) : undefined
            }
            regionMode={regionMode}
            onRegion={(r: Region) => {
              setRegionMode(false);
              void transcribe(r.page, r.rect, r.image);
            }}
            onSelection={setSelection}
            onSourceClick={(sid) => {
              const n = ordered.find((x) => x.source_id === sid);
              const s = sources.find((x) => x.id === sid);
              if (n) setSelectedId(n.id);
              else if (s && s.kind === "region" && s.text) setSnippet(s); // reopen a figure not yet carded
            }}
          />
        ) : (
          <section className="reader welcome">
            <p>
              Open lecture slides or a handout (PDF, PPTX, DOCX) with <kbd>O</kbd> or drop a file here.
            </p>
          </section>
        )}
        <Cards
          notes={ordered}
          sourceLabels={sourceLabels}
          selectedId={selectedId}
          editing={editing}
          draft={draft}
          sendErrors={sendErrors}
          onSelect={setSelectedId}
          onEdit={setEditing}
          onCancel={() => {
            setEditing(null);
            setDraft(null);
          }}
          onSave={save}
          onCreate={(f) => void create({ ...f, sel: draft?.sel })}
          onShowSource={(sid) => reader.current?.showSource(sid)}
          onDismissFlag={(id, flag) => void dismissFlag(id, flag)}
          edits={edits}
          askingFor={askingFor}
          onAsk={(id, t) => void askEdit(id, t)}
          onCancelAsk={() => setAskingFor(null)}
          onAccept={(j) => void accept(j)}
          onDiscard={(j) => void discard(j)}
          onRetryEdit={(j) => void guard(api.retryJob(j.id)).then(reloadJobs)}
          onCancelJob={(j) => void guard(api.cancelJob(j.id)).then(reloadJobs)}
        />
      </main>
      {jobsOpen && (
        <JobsPanel
          jobs={jobs}
          onClose={() => setJobsOpen(false)}
          onChanged={() => void reloadJobs()}
          onShowSource={(sid) => reader.current?.showSource(sid)}
          say={say}
        />
      )}
      {historyOpen && doc && (
        <HistoryPanel
          docId={doc.id}
          version={notes}
          onPick={(e) => void step(e.undone ? "redo" : "undo", e.id)}
          onClose={() => setHistoryOpen(false)}
        />
      )}
      {exportOpen && doc && (
        <ExportDialog
          doc={doc}
          allDocIds={docs.map((d) => d.id)}
          onDone={(r) => {
            setExportOpen(false);
            say(`Exported ${r.cards} card${r.cards === 1 ? "" : "s"} to ${r.name}${r.marked ? " · marked exported, so Send skips them" : ""}`);
            void refresh(doc.id);
          }}
          onClose={() => setExportOpen(false)}
        />
      )}
      {docConfirm && (
        <DocumentConfirm estimate={docConfirm} onSubmit={(f) => void generateDocument(f)} onCancel={() => setDocConfirm(null)} />
      )}
      {settingsOpen && settings && (
        <SettingsDialog
          settings={settings}
          anki={anki}
          onChange={setSettings}
          onAnkiRead={(st) => {
            setAnki(st);
            if (docId) void guard(refresh(docId));
          }}
          onClose={() => setSettingsOpen(false)}
        />
      )}
      {toast && <div className={`toast ${toast.kind}`}>{toast.text}</div>}
      {help && <Help onClose={() => setHelp(false)} />}
    </div>
  );
}

function DocField(p: { label: string; value: string; placeholder: string; list?: string; onCommit(v: string): void }) {
  const [v, setV] = useState(p.value);
  const commit = () => v !== p.value && p.onCommit(v);
  return (
    <label className="docfield">
      {p.label}
      <input
        value={v}
        placeholder={p.placeholder}
        list={p.list}
        onChange={(e) => setV(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          if (e.key === "Escape") {
            setV(p.value);
            (e.target as HTMLInputElement).blur();
          }
        }}
      />
    </label>
  );
}

function DeckList({ connected }: { connected: boolean }) {
  const [decks, setDecks] = useState<string[]>([]);
  useEffect(() => {
    if (connected) void api.ankiDecks().then(setDecks, () => setDecks([]));
  }, [connected]);
  return (
    <datalist id="decks">
      {decks.map((d) => (
        <option key={d} value={d} />
      ))}
    </datalist>
  );
}

function AnkiPill({ status }: { status: AnkiStatus | null }) {
  if (!status) return <span className="pill bad">Anki ?</span>;
  const checked = indexLine(status.index);
  if (!status.connected)
    return (
      <span className="pill bad" title={[...status.problems, checked].join("\n")}>
        Anki offline
      </span>
    );
  if (status.problems.length)
    return (
      <span className="pill warn" title={[...status.problems, checked].join("\n")}>
        Anki ⚠ {status.problems.length}
      </span>
    );
  return (
    <span className="pill ok" title={checked}>
      Anki ✓
    </span>
  );
}
