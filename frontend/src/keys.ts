// Keyboard shortcuts: one table drives both the key handler and the help sheet. The daily ones are
// on the left of the keyboard, so the right hand can stay on the mouse; the older right-hand keys
// still work.

export type Command =
  | "newCard"
  | "newList"
  | "newCloze"
  | "generate"
  | "generateDocument"
  | "promptCard"
  | "figure"
  | "readShots"
  | "readShotsDirect"
  | "aiEdit"
  | "acceptSuggestion"
  | "discardSuggestion"
  | "next"
  | "prev"
  | "edit"
  | "delete"
  | "undo"
  | "redo"
  | "history"
  | "toggleReverse"
  | "prevPage"
  | "nextPage"
  | "zoomIn"
  | "zoomOut"
  | "zoomFit"
  | "send"
  | "export"
  | "open"
  | "openUrl"
  | "jobs"
  | "settings"
  | "help";

type Shortcut = { command: Command; keys: string[]; help: string; group: "Cards" | "Generate" | "Reader" | "Anki" | "App" };

export const SHORTCUTS: Shortcut[] = [
  { command: "newCard", keys: ["c", "n"], help: "New card (uses the selected text, if any)", group: "Cards" },
  { command: "newList", keys: ["Shift+c", "l"], help: "New list card (one item per selected line)", group: "Cards" },
  { command: "newCloze", keys: ["v"], help: "New cloze card (uses the selected text, if any); in it, Ctrl+Shift+C clozes the selected words, Ctrl+Shift+Alt+C with the same number so they show together", group: "Cards" },
  { command: "generate", keys: ["g"], help: "Generate cards from the selection (type a focus such as MoA, or leave it empty; Tab or Enter generates)", group: "Generate" },
  { command: "generateDocument", keys: ["Shift+g"], help: "Generate cards for the whole document (shows the cost first)", group: "Generate" },
  { command: "promptCard", keys: ["q", "p"], help: "Card from a prompt: say what you want a card on, even if the document doesn't cover it (e.g. why hypoglycaemia causes decerebrate posture)", group: "Generate" },
  { command: "figure", keys: ["b", "i"], help: "Screenshot a figure: drag a box around it (or paste one with Ctrl+V); click to pick, Shift+click to add", group: "Generate" },
  { command: "readShots", keys: ["t"], help: "Read the picked screenshots into text (one call each, joined; again if already read), correct it, then G / C / Shift+C", group: "Generate" },
  { command: "readShotsDirect", keys: ["Shift+t"], help: "Read the picked screenshots and go straight to generating from the text, without correcting it", group: "Generate" },
  { command: "aiEdit", keys: ["a"], help: "Ask the AI to change the selected card (say what to change)", group: "Generate" },
  { command: "acceptSuggestion", keys: ["f", "y"], help: "Accept the AI's suggestion for the selected card", group: "Generate" },
  { command: "discardSuggestion", keys: ["d"], help: "Discard the AI's suggestion", group: "Generate" },
  { command: "jobs", keys: ["`", "."], help: "Show generation jobs: cost, errors, left-out content", group: "Generate" },
  { command: "next", keys: ["Tab", "j", "ArrowDown"], help: "Next card", group: "Cards" },
  { command: "prev", keys: ["Shift+Tab", "k", "ArrowUp"], help: "Previous card", group: "Cards" },
  { command: "edit", keys: ["e", "Enter"], help: "Edit card · Ctrl+S (or Ctrl+Enter) saves · Tab moves between fields · Esc cancels", group: "Cards" },
  { command: "delete", keys: ["x", "Delete"], help: "Delete card", group: "Cards" },
  { command: "undo", keys: ["z", "Ctrl+z"], help: "Undo the last change to the cards", group: "Cards" },
  { command: "redo", keys: ["Shift+z", "Ctrl+Shift+z", "Ctrl+y"], help: "Redo", group: "Cards" },
  { command: "history", keys: ["h"], help: "Undo history: click a change to undo back to it", group: "Cards" },
  { command: "toggleReverse", keys: ["r"], help: "Toggle reverse card (asks for the reverse prompt)", group: "Cards" },
  { command: "prevPage", keys: ["["], help: "Previous page", group: "Reader" },
  { command: "nextPage", keys: ["]"], help: "Next page", group: "Reader" },
  { command: "zoomIn", keys: ["+", "="], help: "Zoom in", group: "Reader" },
  { command: "zoomOut", keys: ["-"], help: "Zoom out", group: "Reader" },
  { command: "zoomFit", keys: ["0"], help: "Fit page width", group: "Reader" },
  { command: "send", keys: ["Shift+s"], help: "Send new and edited cards to Anki (Shift, so a stray S beside D and F sends nothing)", group: "Anki" },
  { command: "export", keys: ["Shift+e"], help: "Export cards as an Anki import file (.txt)", group: "Anki" },
  { command: "open", keys: ["o"], help: "Open a PDF, PPTX or DOCX", group: "App" },
  { command: "openUrl", keys: ["Shift+o"], help: "Open a web page by its address (its article and figures, as a document)", group: "App" },
  { command: "settings", keys: [","], help: "Settings: API key, models, defaults", group: "App" },
  { command: "help", keys: ["?"], help: "Show shortcuts", group: "App" },
];

export type KeyLike = { key: string; ctrlKey?: boolean; metaKey?: boolean; altKey?: boolean; shiftKey?: boolean };

function matches(spec: string, e: KeyLike): boolean {
  const parts = spec.split("+");
  const key = parts.length > 1 && parts[parts.length - 1] === "" ? "+" : parts[parts.length - 1];
  const mods = new Set(parts.slice(0, -1).map((m) => m.toLowerCase()));
  if (!!(e.ctrlKey || e.metaKey) !== mods.has("ctrl")) return false;
  if (!!e.altKey !== mods.has("alt")) return false;
  // letters and named keys (Tab, Enter, ArrowDown): Shift must match, so Tab and Shift+Tab differ
  if (/^[a-z]$/i.test(key) || key.length > 1)
    return e.key.toLowerCase() === key.toLowerCase() && !!e.shiftKey === mods.has("shift");
  return e.key === key; // symbols: Shift is part of how the symbol is typed
}

/** Whether a keydown submits a box. One-line boxes (focus, prompt, AI edit): Enter, or Tab or
 * Ctrl+S for the left hand. The card editor and the transcript ("multiline"): Ctrl+S or Ctrl+Enter,
 * since Tab moves between their fields. Callers prevent the default (focus moving, the browser's
 * Save dialog). */
export function submits(e: KeyLike, box: "line" | "multiline"): boolean {
  const ctrl = !!(e.ctrlKey || e.metaKey);
  if (ctrl && !e.altKey && e.key.toLowerCase() === "s") return true;
  if (box === "multiline") return ctrl && e.key === "Enter";
  return e.key === "Enter" || (e.key === "Tab" && !e.shiftKey && !ctrl && !e.altKey);
}

/** The command for a keydown, or null. Nothing fires while the user is typing in a field. */
export function commandFor(e: KeyLike, typing: boolean): Command | null {
  if (typing) return null;
  for (const s of SHORTCUTS) if (s.keys.some((spec) => matches(spec, e))) return s.command;
  return null;
}

export function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
}
