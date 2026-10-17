# clanki

Read lecture slides and handouts, highlight passages, and turn them into Anki cards for your
own note types (`Basic (optional reversed card)` with a `Why` field, and `Cloze (overlapping)`).
See `design_docs/implementation_plan.md` for the design and roadmap.

Milestone 1 (now): reader + manual cards + send to Anki. LLM generation is milestone 2.

## Set up a Windows PC

1. Install [uv](https://docs.astral.sh/uv/) and [Git](https://git-scm.com/download/win).
2. For PPTX/DOCX files, install [LibreOffice](https://www.libreoffice.org/). PDFs need nothing extra.
3. In Anki: Tools ▸ Add-ons ▸ Get Add-ons ▸ code `2055492159` (AnkiConnect), then restart Anki.
4. `git clone <repo> clanki`, then double-click `clanki.bat`. It opens http://127.0.0.1:8710/.

Update with `update.bat`. Anki must be open to send cards; without it, use Export .txt and
File ▸ Import in Anki.

## Settings

Optional `config.toml` in `%APPDATA%\clanki` (documents and cards live there too):

```toml
data_dir = "D:/OneDrive/clanki"   # share between PCs (use one PC at a time)
port = 8710
anki_url = "http://127.0.0.1:8765"
soffice = "C:/Program Files/LibreOffice/program/soffice.exe"   # if not found automatically
default_deck = "Default"
```

## Using it

Press `?` in the app for all shortcuts. The main loop:

- Select text in the document, press `N` for a card (Back is prefilled) or `L` for a list card
  (one item per bullet or line). `Ctrl+Enter` saves.
- `J`/`K` move between cards, `E` edits, `R` toggles the reverse card and asks for the reverse
  prompt (sent as `Back<br>(r: prompt)`), `X` deletes, `Z` undoes.
- `S` sends new and edited cards to Anki (edited cards are updated in place). Cards with errors
  stay in clanki until fixed. `Shift+E` exports an import file.

## Development (WSL/Linux or Windows)

```sh
uv sync                                   # Python deps
uv run pytest                             # backend tests
cd frontend && npm ci
npm test                                  # unit tests
npm run build && npm run e2e              # build UI, run browser tests
npm run dev                               # UI dev server on :5173 (run `uv run clanki --no-browser` too)
uv run python tests/e2e_server.py         # clanki with a fake Anki and a throwaway data dir
```

The built UI in `src/clanki/static/` is committed: run `npm run build` before committing UI
changes. Never commit lecture material (`samples/` is ignored).
