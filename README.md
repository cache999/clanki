# clanki

Read lecture slides and handouts, highlight passages, and turn them into Anki cards for your
own note types (`Basic (optional reversed card)` with a `Why` field, `Cloze (overlapping)`, and
Anki's own `Cloze`).
See `design_docs/implementation_plan.md` for the design and roadmap.

All milestones are built (3, the prompt-quality loop, was skipped). clanki has:
- a reader, manual and LLM-generated cards (DeepSeek), and AI edits of a card;
- send to Anki, or export with filters, and warnings for cards already in Anki;
- a coverage strip, figures and screenshots read into text, and web pages and papers by address;
- undo history, a settings page, and three prompt profiles: medical, general knowledge, and ML
  papers with MathJax.

## Set up a Windows PC

1. Install [uv](https://docs.astral.sh/uv/) and [Git](https://git-scm.com/download/win).
2. For PPTX/DOCX files, install [LibreOffice](https://www.libreoffice.org/). PDFs need nothing extra.
3. In Anki: Tools ▸ Add-ons ▸ Get Add-ons ▸ code `2055492159` (AnkiConnect), then restart Anki.
4. `git clone <repo> clanki`, then double-click `clanki.bat`. It opens http://127.0.0.1:8710/.

Update with `update.bat`. Anki must be open to send cards; without it, use Export .txt and
File ▸ Import in Anki.

The AI features send the document's text (and any figure you select) to DeepSeek, a third-party
service; the first time you use one, clanki shows a one-time notice about sharing material you may
not have the right to share. For generation, add a [DeepSeek API key](https://platform.deepseek.com/api_keys) in Settings (`,`):
it is stored in Windows Credential Manager. A `DEEPSEEK_API_KEY` environment variable takes
precedence (that is how WSL development works: see below).

## Settings

Settings (`,`) covers the API key, the models, defaults for new documents, and this computer's settings:
the Anki address, LibreOffice path, port and data folder. The last group is saved to
`config.toml` in `%APPDATA%\clanki` (`~/.local/share/clanki` in WSL), which you can also edit by
hand (documents and cards live in that folder too):

```toml
data_dir = "D:/OneDrive/clanki"   # share between PCs (use one PC at a time)
port = 8710
anki_url = "http://127.0.0.1:8765"
soffice = "C:/Program Files/LibreOffice/program/soffice.exe"   # if not found automatically
default_deck = "Default"
```

## Using it

Press `?` in the app for all shortcuts. The daily ones are on the left of the keyboard, so your
right hand can stay on the mouse for selecting (the older right-hand keys `N` `L` `P` `I` `Y` `J`
`K` `.` still work). The boxes you type into submit with `Tab` as well as Enter, and the card
editor and transcript box save with `Ctrl+S`.

The bars follow the order you work in: the top one opens documents and sets the profile and models
(Text model writes and edits cards; Image model reads screenshots, and only lists models that can),
the bottom one has the deck, tags, jobs, and Send and Export. The main loop:

- Select text and press `G` to generate cards from it. Type a focus such as `MoA` to get only
  that, or press `Tab` for everything UKMLA-relevant. `Shift+G` generates for the whole document
  after showing the estimated cost. `` ` `` shows the jobs: progress, cost, errors, and what was left
  out under the UKMLA scope (with "Card this" to card it anyway).
- `Q` makes a card from a prompt, for something the document doesn't cover: type
  `why hypoglycaemia causes decerebrate posture` and press `Tab`. The model writes it from its own
  knowledge (the document only sets the level and terms) and flags what it's unsure of. The card
  sits on the page you were reading, labelled `p.n prompt`.
- Screenshots of figures, labelled diagrams or tables:
  - Press `B` and drag a box around one, or paste a screenshot with `Ctrl+V`. It's saved to the
    tray under the reader bar and picked (filled in). Nothing is sent yet.
  - Click a box or thumbnail to pick it, and `Shift`+click to add others.
  - `T` reads the picked ones with the image model (deepseek-flash, about $0.0002 each): labels
    come out as `label: what it points to`, arrows as `A → B`. Several are read separately and
    joined, each headed `[Image n, p.x]`. Pressing `T` again reads them again.
  - Correct the text, press `Ctrl+S`, then `G` / `C` / `Shift+C` as for selected text.
  - `Shift+T` reads them and goes straight to the focus box, without correcting: for plain text
    that needs no checking.
  - Drag a thumbnail onto a card to add the image to the field you drop it on (Front, Back, Why;
    a list's Remarks or Sources). Send to Anki copies the image into Anki; export files can't carry
    images.
  - For Image Occlusion cards, use Anki's own editor.
- `Shift+O` (or Web page…) opens a web page by its address: its article and figures become a
  document like any other. Sites that block apps (e.g. Geeky Medics) or need a login can't be
  fetched; save the page from the browser instead (`Ctrl+P`, Save as PDF) and open that.
- Or select text and press `C` for a card (Back is prefilled) or `Shift+C` for a list card
  (one item per bullet or line). `Tab` moves between fields; `Ctrl+S` saves.
- `V` makes a cloze card (Anki's `Cloze` note type; its Why is the `Extra` field). Select words in
  its text and press `Ctrl+Shift+C` to cloze them with the next number, or `Ctrl+Shift+Alt+C` to
  reuse the last number so they show together on one card, as in Anki. The medical profile writes
  clozes itself only where a Q/A or list fits badly: properties asked together (a title line, an
  empty line, then `Fatigue: {{c1::resistant vs prone}}` lines) and facts whose question would be
  too wordy. Type `cloze` as the focus after `G` to ask for clozes.
- `Tab`/`Shift+Tab` move between cards, `E` edits, `R` toggles the reverse card and asks for the
  reverse prompt (sent as `Back<br>(r: prompt)`), `X` deletes, `Z` undoes.
- `A` asks the AI to change the selected card: type what to change (`shorter front`,
  `split into two`, `make it a list`) and press `Tab`. The suggestion appears under the card as a
  diff; `F` accepts it, `D` discards it. The card stays as it was until you accept.
- `Shift+S` sends new and edited cards to Anki (edited cards are updated in place). It needs Shift
  so a stray `S` beside `D` and `F` sends nothing. Cards with errors stay in clanki until fixed.
- `Shift+E` exports an import file. Choose new and edited or all cards, Q/A, lists and/or clozes, a tag,
  and this document or all of them. Exported cards are marked `exported` so `Shift+S` skips them. Import
  the file in Anki with File ▸ Import. To update an exported card after editing it, export it again:
  the re-import updates it in Anki.
- `Z` undoes any change to the cards (edits, deletes, generated batches, accepted AI edits) and
  `Shift+Z` redoes it. `H` lists the changes; click one to undo back to it. The history survives
  restarts.
- Each document has a profile (top bar), which decides how cards are written:
  - **Medical (UKMLA)**: the default.
  - **General knowledge**: any subject.
  - **Machine learning (papers)**: names the method on every card and writes equations in MathJax
    (`\( … \)`), which Anki and clanki's card list render.

  Opening an arXiv or bioRxiv link with `Shift+O` fetches the paper's PDF. A downloaded PDF works
  too. Settings ▸ "For new documents" sets the default profile, deck and tags.
- A card that repeats one already in Anki gets a ⚠ showing that card: the same subject asked about
  the same subquestion (`Sacubitril (MoA)` when Anki has `Sacubitril (MoA, use) [2]`), regardless
  of word order. So does a reverse card whose Back a reversed Anki card already has. clanki reads
  your Anki cards (about a second) when Anki is open and every 10 minutes after; Settings ▸
  Re-read Anki does it now. The warnings keep working while Anki is closed.
- The strip beside the reader shows each page's coverage: green has cards (darker is more), amber
  is generating, red failed. Click it to go to that page.
- The model is told to use your subquestion words (`MoA`, `function`, `attachments`, …): clanki's
  list plus the ones you use most in Anki, shown in Settings. Edit `profile.toml` in
  `src/clanki/prompts/medical_ukmla/` to change the list or exclude words.

## Run it from WSL

The built UI is committed, so uv is all you need (no npm):

```sh
cd ~/clanki
uv sync                         # first time, and after pulling
uv run clanki --no-browser      # Ctrl+C stops it
```

Then open http://localhost:8710/ in your Windows browser. Windows forwards `localhost` to WSL, so
this works in WSL's default (NAT) networking. Files opened with `O` can come from anywhere on
Windows; they are uploaded to clanki.

- **API key**: set `DEEPSEEK_API_KEY` in the shell that runs clanki. Keep it in
  `~/.config/clanki/env` (`chmod 600`, lines like `DEEPSEEK_API_KEY=sk-…`) and load it at the top
  of `~/.bashrc`, above the interactive-only guard:

  ```sh
  [ -f ~/.config/clanki/env ] && { set -a; . ~/.config/clanki/env; set +a; }
  ```

  Don't save a key from Settings in WSL: there is no credential store, so it hangs.
- **Data**: documents, cards and `config.toml` live in `~/.local/share/clanki`, separate from a
  Windows install's `%APPDATA%\clanki`. Keep them on the Linux side (SQLite on `/mnt/c` is slow).
- **PPTX/DOCX**: need LibreOffice in WSL (`sudo apt install libreoffice`). PDFs need nothing.
- **Sending to Anki** needs WSL's mirrored networking, where `127.0.0.1` is shared with Windows:
  add `networkingMode=mirrored` under `[wsl2]` in `%UserProfile%\.wslconfig` and run
  `wsl --shutdown` in PowerShell (it applies to all of WSL). Under the default NAT networking,
  clanki can't reach Anki and `Shift+S` reports it unavailable; export instead (`Shift+E`, then
  File ▸ Import in Anki; re-importing updates cards rather than duplicating them).
- **A sandbox that costs nothing**: `uv run python tests/e2e_server.py` runs the whole app at
  http://localhost:18710/ with a fake LLM, a fake Anki and a throwaway data folder, alongside the
  real one if you like. The fake LLM makes a card from the first selected line and, for AI edits,
  sets the Front to `Edited: <your instruction>`. Add `--real-llm` to use DeepSeek with the fake
  Anki and throwaway data.

## Development (WSL/Linux or Windows)

```sh
uv sync                                   # Python deps
uv run pytest                             # backend tests (no network, no keys)
uv run pytest -m live                     # real DeepSeek calls, needs DEEPSEEK_API_KEY (~$0.002)
cd frontend && npm ci
npm test                                  # unit tests
npm run build && npm run e2e              # build UI, run browser tests
npm run dev                               # UI dev server on :5173 (run `uv run clanki --no-browser` too)
uv run python tests/e2e_server.py         # clanki with a fake Anki, a fake LLM and throwaway data
uv run python tests/e2e_server.py --real-llm   # same, but real DeepSeek (costs money)
```

The prompt lives in `src/clanki/prompts/medical_ukmla/system.md`.

The built UI in `src/clanki/static/` is committed: run `npm run build` before committing UI
changes. Never commit lecture material (`samples/` is ignored).
