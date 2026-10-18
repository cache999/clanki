# clanki: implementation plan

Status: ready to implement, 2026-10-17. Builds on `web_gui_spec.md` and `claude_skill.md`. Milestone 0 is done: all import tests passed and the Why field has been added.

## Decisions

| Topic | Decision |
|---|---|
| Where it runs | Locally on each Windows PC that has Anki. Python server on `127.0.0.1`, UI in the browser. No hosting, no login. Developed in WSL, but code must run natively on Windows: `pathlib` only, nothing POSIX-only, no hard-coded paths. |
| Sources | PDFs with a text layer. PPTX/DOCX converted to PDF with LibreOffice (`soffice --headless --convert-to pdf`); when LibreOffice is missing, ask the user to "Save as PDF" from Office. Figures (a dragged box) and pasted screenshots, read into text by deepseek-flash. Web pages by URL, laid out as PDF (milestone 5). |
| Sources (later) | Whole scanned PDFs with no text layer. |
| Anki delivery | AnkiConnect is primary: send, update, read note types, duplicate checks, facet vocabulary. A `.txt` export is the fallback. |
| Basic explanations | 4th field `Why` on `Basic (optional reversed card)` (added), shown on both answer sides. |
| Reverse cards | When Add Reverse is on, the Back must also carry a prompt that recovers the Front, written into the Back text: `Paris<br>(r: what country has this capital?)`. Stored as its own field in clanki and joined into Back on send/export. |
| LLM | DeepSeek first (decided 2026-10-17): `deepseek-flash` by default, `deepseek-v4-pro` selectable, through its OpenAI-compatible API. The provider layer stays pluggable; a Claude provider is future work. |
| API keys | Environment variable first (`DEEPSEEK_API_KEY`, later `ANTHROPIC_API_KEY`; in WSL from `~/.config/clanki/env`), then the OS credential store (Windows Credential Manager via `keyring`), entered in a Settings dialog that never shows the key back. |

## Your Anki setup (read from the collection, read-only)

- **`Basic (optional reversed card)`**: Front, Back, Add Reverse, Why. 15,255 notes; Add Reverse is set on 724 of them. Card 2 (reverse) shows Back as its prompt, which is why reversed Backs need the `(r: …)` prompt.
- **`Cloze (overlapping)`**: Title, Original, Mnemonic, Remarks, Sources, Settings, Text1–Text20, Full (27 fields). Title comes first, but the builder in `claude_skill.md` assumed Original first. Its output would have filled the wrong fields on every list note.
- **How you actually make lists** (this differs from the old skill, and the prompt follows your practice): settings are always `1,1,0 | n,n,n,n` with the whole-list card on. Sets get an imposed order (top-down anatomy, severity, frequency), stated in the Title or Remarks. `Original` uses `<br>` lines or `<ul>`. The Text fields wrap items in `<div>` or `<li>` to match.
- Cloze Overlapper for 23x is installed (supports Anki up to 23.12.1). clanki fills Text1–20 and Full itself, so the add-on isn't needed when importing or sending (confirmed by test 1).
- AnkiConnect (add-on code `2055492159`) is installed and verified on Anki 25.09.2 (2026-10-18).

## Architecture

```
Browser (React + TS, PDF.js) ──HTTP────▶ FastAPI (Python, uv) ──▶ SQLite (data dir)
                                              ├─▶ LLM provider: DeepSeek (Claude later)
                                              ├─▶ LibreOffice (PPTX/DOCX → PDF)
                                              └─▶ AnkiConnect  http://127.0.0.1:8765
```

- **Backend**: Python ≥3.12 managed by `uv`, with FastAPI and Uvicorn. SQLite through `sqlite3` with a thin repository layer. Background jobs run on a thread pool (default concurrency 3); the UI polls job status once a second while jobs are active (simpler than Server-Sent Events and fast enough locally).
- **Frontend**: React, TypeScript and Vite, with `pdfjs-dist` for the viewer and its text layer. The built UI (`src/clanki/static/`) is committed, so other PCs need only `uv` and Git (plus LibreOffice for PPTX/DOCX), not Node.
- **Install on a PC**: install uv and Git, clone the repo, double-click `clanki.bat` (runs `uv run clanki` and opens the browser); `update.bat` pulls updates. See `README.md`.
- **Config and data**: stored in `%APPDATA%\clanki` (via `platformdirs`), holding `config.toml` (API keys, default model, port, data dir) and `clanki.db` plus the uploaded files. The data dir can be pointed at OneDrive to share state between PCs, but then use only one PC at a time.
- **AnkiConnect**: the backend calls it on localhost. On Windows both run on the same host, so no CORS setup is needed. (Dev in WSL needs WSL mirrored networking, or a stub.)

## UI

```
┌ [doc tabs]  p.12/40  zoom  │ Profile: Medical (UKMLA) │ Model: … │ Jobs ●2 ⚠1 │ Send ▸ Anki ┐
├───────────────────────────────────────────────┬───────────────────────────────┤
│ READER (~65%)                                  │ CARDS (~35%)                   │
│ PDF.js pages with selectable text              │ Filter: doc │ page │ selection │
│ Highlights: amber = queued/running             │ Grouped by source, doc order   │
│             green = has cards (click → cards)  │ ┌ fact · MoA ────────────────┐ │
│ Selection → floating bar:                      │ │ Sacubitril (MoA, use) [2]  │ │
│   Focus: [ MoA        ]  ⏎ generate            │ │ → Neprilysin inhibitor; HF │ │
│ Coverage strip beside the scrollbar            │ │ Why ▸  · tags · ⚠ warnings │ │
│                                                │ └ new │ sent ✓ │ edited ●  ───┘ │
└────────────────────────────────────────────────┴───────────────────────────────┘
```

- Clicking a card scrolls the reader to its source highlight, and clicking a highlight filters the cards to it.
- The jobs popover lists each job's state, elapsed time, tokens and cost, with retry and cancel. A failed job keeps its highlight marked red.
- Each job's details list the content the model **left out** under the UKMLA scope, each with a "card this anyway" button. This makes the relevance filter auditable.

### Keyboard shortcuts

Single keys, active whenever you are not typing in a field; `?` shows the full sheet (defined in `frontend/src/keys.ts`). There is no pane focus: `N`/`L` use the current text selection if there is one. Browser-reserved combinations (e.g. Chrome's `Ctrl+Shift+A`) are avoided.

| Key | Action |
|---|---|
| `N` / `L` | New card / new list card, from the selection if any (Back prefilled; one list item per bullet or line) |
| `G` | Generate from the selection: opens the focus box; Enter with it empty runs unconditioned generation |
| `P` | Cards from your own prompt: the model's knowledge, no document context |
| `Shift+G` | Generate for the whole document, after a cost estimate |
| `A` | Ask the AI to change the selected card (type what to change); the suggestion shows as a diff |
| `Y` / `D` | Accept / discard the AI's suggestion on the selected card |
| `.` / `,` | Jobs panel / Settings |
| `J` `K` (or `↓` `↑`) | Next/previous card; the reader scrolls to its highlight |
| `E` / `Enter` | Edit; `Ctrl+Enter` saves, `Esc` cancels |
| `X` / `Z` / `Shift+Z` / `H` | Delete / undo / redo / undo history |
| `R` | Toggle Add Reverse; turning it on opens the reverse-prompt box |
| `[` `]`, `+` `-` `0` | Previous/next page, zoom, fit width |
| `S` | Send new and edited cards to Anki |
| `Shift+E` | Export `.txt` |
| `O` / `Shift+O` | Open a document / a web page by its address |
| `I` | Screenshot a figure: drag a box around it (or paste one with `Ctrl+V`); click picks one, `Shift`+click adds more |
| `T` / `Shift+T` | Read the picked screenshots into text (one call each, joined) / read them again; then `Ctrl+Enter` and `G`/`N`/`L` |

## Generation pipeline

**Request layout**, ordered for prompt caching (DeepSeek caches shared prefixes automatically): profile system prompt → facet vocabulary → document text → (uncached) task: the target passage plus the focus text.

- **Highlight job**: the target is the selected text. The surrounding page text and section headings go in as *context only*. They let the model write context-free prompts (no "this drug"), but it cards only the target.
- **Whole-document job**: split into chunks of about 4–6 pages, at headings where they can be detected. Each chunk is its own job with the whole document as the cached prefix. Jobs run in parallel and cards appear chunk by chunk. A final deterministic pass flags duplicates across chunks.
- **Focus text** (e.g. "MoA") narrows the scope: only cards on that facet. With no focus, scope is UKMLA-relevant content, and everything left out is listed with a reason.

**Output schema** (validated with Pydantic; one retry on invalid output):

```json
{
  "cards": [
    {"type": "qa", "front": "...", "back": "...", "why": "...", "add_reverse": true,
     "reverse_prompt": "what country has this capital?",
     "n_answers": 2, "facets": ["moa", "use"], "kind": "fact|linkage|concept", "tags": [], "flags": []},
    {"type": "list", "title": "...", "items": ["..."], "ordered": true, "order_principle": "top-down anatomy",
     "remarks": "...", "mnemonic": "", "full": true, "kind": "process|set", "tags": [], "flags": []}
  ],
  "left_out": [{"text": "...", "reason": "not UKMLA-relevant"}],
  "image_occlusion_candidates": ["p.7 figure: brachial plexus"],
  "flags": ["source says X; current NICE guidance says Y — check"]
}
```

- **DeepSeek**: JSON output mode (`response_format: json_object`, with the schema and an example in the prompt) through its OpenAI-compatible endpoint, thinking on, configurable effort. Cost from the reported cache-hit, cache-miss and output tokens at the peak or off-peak rate in force.
- **Claude (future work)**: structured outputs (`output_config.format`) with adaptive thinking and prompt caching on the stable prefix, validated against the same schema.
- **Deterministic validators** (ported from `build_anki_import.py`; results show as ⚠ on cards):
  - Two cards share a Back (the reverse card would be ambiguous).
  - A list has fewer than 2 or more than 20 items (warn above 8), or an item contains `::` `{{` `}}`.
  - A list has no title.
  - The `[n]` marker doesn't match the number of answers.
  - A Basic Back has 4 or more `;` items (suggest a list instead).
  - The Front contains answer words (a giveaway).
  - Add Reverse is on but there is no reverse prompt. (A "reverse prompt repeats Front words" check was dropped: it flags good prompts such as `what country has this capital?` for `Capital of France`.)
  - The Front matches an existing Anki note (via AnkiConnect).
  - HTML outside the whitelist (`b i u sub sup br`).

## Prompt profiles

`prompts/<profile>/`, hard-coded in the repo and selectable per document:

- `system.md`: card-writing rules.
- `examples.md`: worked examples.
- `profile.toml`: default deck and tag prefix, scope rule, whole-list policy, facet sets.

`medical_ukmla` (the default) is adapted from `claude_skill.md`, corrected to your note types and conventions:

- Telegraphic fronts. Subquestions go in brackets, e.g. `(MoA, use)`, with `[n]` when more than one answer is needed. Related facts whose recall is largely shared share one card. If `n` grows beyond about 3, make a list instead.
- Subquestions must be generic, taken from the facet vocabulary (below), so one card's unusual question doesn't become the cue for its answer.
- Add Reverse only when the Back, together with a short reverse prompt, pins down exactly one Front. Every reversed card gets that prompt: it says which dimension of the Front to recall, is telegraphic like a Front (`scar?`, `what country has this capital?`), and contains no Front words. If no such prompt exists, Add Reverse stays off.
- Back is short. Reasoning goes in Why (Remarks for lists), following the skill's UKMLA standard: physiology first, never invent a mechanism, name the guideline source.
- Sets get an imposed, stated order.
- Nothing from `[note for llms]` ever appears in a card.

`general` (any subject) and `ml_papers` (machine-learning papers, MathJax) were added in milestone 6; each document picks its profile.

## Facet vocabulary (the "cache" from your Sacubitril note)

Mined from your 15,255 Basic fronts, the most common bracketed subquestions are:

| Facet | Count |
|---|---|
| definition (+ "def") | 892 |
| function | 468 |
| location | 390 |
| MoA | 341 |
| origin | 130 |
| attachments | 112 |
| pathophysiology | 103 |
| name | 99 |
| structure | 80 |
| use | 71 |
| cause(s) | 66 |
| insertion | 57 |
| innervation | 52 |

Answer counts: `[2]` is used 861 times, `[3]` 252, `[4]` 61.

How the cache works (built in milestone 4):

- Facet counts are mined from Anki through AnkiConnect, as part of the Anki snapshot (`anki_index.py`). Only abbreviations are normalised (`def` → definition, `pathophys` → pathophysiology); `causes` and `functions` stay distinct from `cause` and `function`.
- Facets are grouped by entity type in the system prompt. For a drug: MoA, use, class, adverse effects, contraindications, monitoring. For a nerve: origin, course, innervation.
- The model gets the curated list in `profile.toml` plus your most used other facets (up to 50 in all), and is told to prefer them. A new facet is allowed but flagged on the card.
- Counts update when sent cards are read back from Anki. Every drug card is then asked the same generic questions, which avoids one-offs like "is it a prodrug?" on a single card.

## Data model (SQLite)

- `documents`: id, title, kind, file path, page count, profile, default deck.
- `sources`: id, document_id, kind (`highlight`/`chunk`/`ocr`), page range, text, anchor (PDF.js page + text-content offsets, so highlights survive reloads).
- `jobs`: id, source_id, focus, provider/model, status, tokens in/out, cost, error, raw response, left_out, flags, timestamps.
- `notes`:
  - id, `guid`, source_id, job_id, type, all fields, deck, tags, warnings.
  - status: `new`/`sent`/`edited`/`deleted` (soft delete, so undo works).
  - anki_note_id, sent_at.
- `settings`: key/value, including `anki_index`, the snapshot of the Anki collection (notes and facet counts).

The `guid` is generated when a card is created. It makes `.txt` re-imports update notes instead of duplicating them, which test 3b checks. AnkiConnect updates use `anki_note_id`.

## Anki delivery

1. **AnkiConnect**:
   - On startup, call `version` and `modelFieldNames` for both note types and check that the field order matches the profile. Show a banner if, for example, Why is missing.
   - Send with `addNotes`; for already-sent notes edited in clanki, use `updateNoteFields`.
   - Before sending, run `findNotes` on each Front to warn about duplicates.
   - The deck is chosen at send time.
   - When Add Reverse is on, Back is assembled on send as `back + "<br>(r: " + reverse_prompt + ")"`. The format string lives in `profile.toml`.
2. **`.txt` export**: the test 3 format (GUID, note type, deck and tags columns, then fields), confirmed working, including GUID-based updates on re-import. Back is assembled the same way as on send.

## Milestones

0. **Import tests: done.** All passed, and the Why field has been added.
1. **Reader and manual cards, no LLM: done 2026-10-17.**
   - Repo skeleton, `clanki.bat`, config.
   - Open PDF/PPTX/DOCX; PDF.js reader with selection.
   - Cards sidebar with full keyboard CRUD.
   - Validators, `.txt` export, AnkiConnect send.

   This is already useful as a faster manual workflow.
2. **LLM generation: done 2026-10-17** (DeepSeek; first live results on the vision handout: 7 cards from one page in 19 s for $0.006 uncached):
   - Provider layer with DeepSeek, `medical_ukmla` prompt, schema.
   - API keys: environment variable or Settings dialog (credential store).
   - Job queue with polling and the jobs indicator.
   - Highlight anchoring, focus conditioning, whole-document chunking.
   - Cost display.
   - AI edits: revise one card from an instruction (same cached prefix plus the card and its source). The suggestion waits as a diff until accepted or discarded, and asking again replaces it. Accepting a change to a card already in Anki marks it `edited`. A type change (Q/A ↔ list) on a sent card replaces it, because Anki cannot change a note's type, and tells you to delete the old note in Anki. A split adds the extra cards from the same source. Accept is refused if the card changed after the request.
3. **Quality loop**: build an eval from 2–3 of your real handouts plus cards you'd accept. Compare DeepSeek Flash and V4 Pro side by side (Claude models once that provider exists), and pick defaults per mode (e.g. a cheap model for the whole-document first pass, a stronger one for highlights).
4. **Anki-aware: done 2026-10-18** (milestone 3 skipped for now: card quality is already good):
   - AnkiConnect verified against the real Anki from WSL with mirrored networking (status check, then add, update and delete in `clanki-test`).
   - `anki_index.py` is a snapshot of every Basic and list note (Front/Title, Back without the reverse prompt, Add Reverse, deck). It is read when a status poll finds it missing or over 10 minutes old, and by Settings ▸ Re-read Anki. Reading 17,736 notes takes about 1.5 s. The snapshot is kept in the `settings` table, so warnings work while Anki is closed. Cards that clanki sends are counted on the next read.
   - Duplicate warnings, on cards not yet sent:
     - the same entity (compared as a set of content words, so word order and small words don't matter), asked with a shared facet, or with no facets on either side;
     - a reverse card with the same Back as a reversed Anki card.

     Run against your own collection, 2% of notes match another one in it, mostly identical fronts or a shared facet.
   - Facet vocabulary (`facets.py`): bracketed subquestions are mined from the Basic fronts, and only abbreviations are normalised (`def`, `pathophys`, `desc`), because plurals ask for several answers. The prompt gets the curated list from `profile.toml`, then your most used other facets (at least 5 uses, up to 50 in all, alphabetical so the cached prefix stays stable). Vague ones (`describe`, `overview`, `brief`, …) are excluded. Settings shows the list.
   - Coverage strip beside the reader: one segment per page, green by number of cards (a chunk's cards spread over its pages), amber while generating, red on failure; click to jump.
5. **Figures and web: done 2026-10-18** (image cards stay in Anki's own Image Occlusion editor):
   - `I` and drag a box on a page: pdf.js renders just that box at about 1300×1300 pixels' worth, the most deepseek-flash reads per image (it now accepts images: `deepseek-v4-flash-vision-exp` was folded into V4.1-Flash on 2026-10-17). `Ctrl+V` pastes a screenshot instead. Each is a source (`region` or `image`), and its image is kept in the document's folder, so retry works.
   - A transcription job (plain text, no JSON mode) uses `prompts/<profile>/transcribe.md`: all text exactly as written, labels as `label: what it points to`, links as `A → B` (inhibition `⊣`), tables as `a | b` rows. The page's own text goes along, to spell labels. A synthetic RAAS diagram came back fully right in 2.7 s for $0.00013, including the label on each arrow and the inhibitor's target.
   - The transcription opens in an editable box in the reader bar. `Ctrl+Enter` makes it the selection, so `G`/`N`/`L` work as for selected text. Generation uses mode `figure` (the prompt says the target was transcribed from a figure), and the cards attach to the figure's source. The box shows as a dashed outline; clicking an uncarded one reopens its text.
   - Web pages: httpx with a user agent that names clanki (Wikipedia refuses anonymous clients), then readability-lxml for the article (it kept TeachMeAnatomy's headings and figures, where trafilatura flattened them), then fpdf2 with a bundled DejaVu font (for symbols like Na⁺) for the PDF. Lists, tables as `a | b` rows, figures and captions are kept, and citation markers dropped. A link to a PDF opens that PDF. A refused or login-only page explains how to save it from the browser. LibreOffice isn't used, because its HTML import needs Writer.
6. **Polish: done 2026-10-18**:
   - **Undo history:** an `actions` table records each change to cards: add, edit, delete, reverse, flag dismissal, accepted AI edit, and a generation job's batch. Each record holds before and after snapshots of the cards it touched, per document.
     - `Z` undoes the latest change and `Shift+Z` redoes it; `H` lists changes and can undo back to any of them. A new change clears redo.
     - Restoring keeps a card's Anki link. A card in Anki whose content changes becomes `edited`, and undoing the creation of a sent card says it is still in Anki.
   - **Export filters:** new and edited or all cards, card types, a tag (including tags under it and the document's tags), and one or all documents, with a live count. Cards with errors are left out.
     - The `exported` status (with `exported_at`) means Send skips the card. An edited exported card is refused by Send (export it again; its guid makes the re-import update it).
   - **Settings page:**
     - Defaults for new documents (deck, tags, profile) are saved in the database.
     - This PC's settings (Anki address, LibreOffice path, port, data folder) go to `config.toml`. The file is edited line by line, so comments survive. The Anki address and LibreOffice path apply at once; port and data folder after a restart.
     - In WSL the system keyring is never used, because GNOME Keyring prompts or hangs there. The key comes from `DEEPSEEK_API_KEY`.
   - **Profiles:** each document has a profile, and every job uses its document's profile. Each profile folder has `system.md`, `transcribe.md`, `profile.toml` (label, scope wording, facets, and `use_anki`: only the medical profile mines Anki facets) and optionally `example.json`.
     - `general`: any subject.
     - `ml_papers`: names the method on every card, uses MathJax, reconstructs equations garbled by PDF text extraction (and flags any it is unsure of), and states results with dataset and metric. A live run on "Attention Is All You Need" reproduced the attention formula from the garbled text for $0.004.
     - MathJax: list items have `}}` and `{{` spaced apart on export, so a formula can't end a cloze early. The HTML check ignores maths, and clanki's card list renders it with KaTeX.
     - Paper links: arXiv `/abs`, `/pdf` and `/html` links and any page with `citation_pdf_url` metadata (bioRxiv, journals) open the paper's PDF under its title.
   - The `general` profile is for anyone: no student or background assumptions, and it follows the source's spelling.
   - Screenshot cache, added after milestone 6:
     - `I` and paste only save a screenshot (a `region` or `image` source with its image). Nothing goes to the model until `T`.
     - Screenshots show in a tray and, for boxes, on the page: dashed when not picked, filled when picked. Click picks one, `Shift`+click toggles more, and the newest is picked alone.
     - `T` runs one transcription job per picked screenshot, skipping any already read unless `Shift+T`. The texts are joined in picking order, each headed `[Image n, p.x]` when there are several.
     - Cards made from several screenshots attach to the first. Each screenshot keeps its own transcript; a single one's text is replaced by the corrected snippet.
     - Dragging a thumbnail onto a card shows drop targets for its fields (`media.IMAGE_FIELDS`); dropping appends `<img src="clanki-<source id>.<ext>">`.
     - Send copies those images into Anki with `storeMediaFile`. clanki shows them via `/api/media/<name>`, and they are the only images the HTML rules allow.
     - The AI never sees image tags: they are stripped from an AI edit's card and put back into its suggestion. The export dialog says how many cards have images (an import file can't carry them; `.apkg` export is future work).
   - Own-prompt cards (`P`), added after milestone 6:
     - The user types a request, and a `prompt` job (`build_prompt_messages`) sends the profile's system prompt and the request, with no document.
     - The model writes from established knowledge, flags anything uncertain, and matches the amount to the request. A live run turned "Frank-Starling law" into 8 core cards for $0.003.
     - The request becomes a `prompt` source at the page being read. Its cards are labelled "own" and left out of coverage. AI edits of them leave the document out too.
   - Third-party notice: before the first AI action (generate, whole document, AI edit, reading a figure or screenshot, card-this-anyway, retry), a one-time dialog says what is sent to DeepSeek. It warns against sending others' intellectual property and confidential or patient data. Accepting is stored with the data (`llm_notice_accepted_at`). The dialog, not a button, takes focus, so the Enter that triggered the action can't accept it.

## Import tests (milestone 0, done)

`design_docs/import_tests/` holds the test files and their generator, `make_import_tests.py`. All four imported correctly:

- **Test 1**: your notes format.
- **Test 2**: rendered cards into Basic.
- **Test 3**: clanki's mixed-type format with a GUID column.
- **Test 3b**: re-import updates notes in place.

Two consequences:

- List notes that clanki fills in work without the Cloze Overlapper add-on.
- Test 3 is the `.txt` export format.

The `Why` field is set up on both card templates as `{{#Why}}<hr><div class=why>{{Why}}</div>{{/Why}}`.

## LLM access

- **Subscription**: Pro includes no API access. Max 5x and 20x include $100/$200 per month of API credits. To use them, link a Console organization under claude.ai ▸ Settings ▸ Billing; the credits then pay for Messages API calls made with that organization's API key. Anthropic tells developers to use API keys and doesn't let apps offer claude.ai login, so clanki uses an API key.
- **Claude models** (per MTok, input/output): Opus 5.5 $4/$20, Sonnet 5.5 $2/$10, Haiku 5.5 $0.10/$0.50, Fable 5.1 $10/$50. All accept images and PDFs and support structured outputs, prompt caching and batches.
- **DeepSeek** (official pricing page, 2026-10-17; peak rate, off-peak is half):
  - `deepseek-flash` (V4.1-Flash): $0.30/$1.20, accepts images.
  - `deepseek-v4-pro`: $1.32/$3.96, text only.
  - Handout text is sent to DeepSeek's servers; check this is acceptable for course material.
- **Rough cost per 10-page handout** (about 10k tokens in, 5k out, before thinking tokens; thinking can add 2–4× to the output cost):

  | Model | Cost |
  |---|---|
  | Opus 5.5 | ~$0.14 |
  | Sonnet 5.5 | ~$0.07 |
  | DeepSeek V4 Pro | ~$0.03 |
  | DeepSeek Flash | ~$0.01 |

  A single highlight costs cents or less.

## Open items

- Claude provider (Anthropic API): deferred to future work on 2026-10-17; testing uses DeepSeek.
- Default model: decided in milestone 3.
- Sharing data between PCs: per-PC by default; OneDrive data dir is optional.
- Whole-list card policy: follows your practice (always on). The old skill turned it on only for ordered lists of 5 items or fewer; this is configurable in `profile.toml`.
