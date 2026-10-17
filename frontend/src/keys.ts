// Keyboard shortcuts: one table drives both the key handler and the help sheet.

export type Command =
  | "newCard"
  | "newList"
  | "generate"
  | "next"
  | "prev"
  | "edit"
  | "delete"
  | "undo"
  | "toggleReverse"
  | "prevPage"
  | "nextPage"
  | "zoomIn"
  | "zoomOut"
  | "zoomFit"
  | "send"
  | "export"
  | "open"
  | "help";

type Shortcut = { command: Command; keys: string[]; help: string; group: "Cards" | "Reader" | "Anki" | "App" };

export const SHORTCUTS: Shortcut[] = [
  { command: "newCard", keys: ["n"], help: "New card (uses the selected text, if any)", group: "Cards" },
  { command: "newList", keys: ["l"], help: "New list card (one item per selected line)", group: "Cards" },
  { command: "generate", keys: ["g"], help: "Generate cards from selection (milestone 2)", group: "Cards" },
  { command: "next", keys: ["j", "ArrowDown"], help: "Next card", group: "Cards" },
  { command: "prev", keys: ["k", "ArrowUp"], help: "Previous card", group: "Cards" },
  { command: "edit", keys: ["e", "Enter"], help: "Edit card · Ctrl+Enter saves · Esc cancels", group: "Cards" },
  { command: "delete", keys: ["x", "Delete"], help: "Delete card", group: "Cards" },
  { command: "undo", keys: ["z", "Ctrl+z"], help: "Undo delete", group: "Cards" },
  { command: "toggleReverse", keys: ["r"], help: "Toggle reverse card (asks for the reverse prompt)", group: "Cards" },
  { command: "prevPage", keys: ["["], help: "Previous page", group: "Reader" },
  { command: "nextPage", keys: ["]"], help: "Next page", group: "Reader" },
  { command: "zoomIn", keys: ["+", "="], help: "Zoom in", group: "Reader" },
  { command: "zoomOut", keys: ["-"], help: "Zoom out", group: "Reader" },
  { command: "zoomFit", keys: ["0"], help: "Fit page width", group: "Reader" },
  { command: "send", keys: ["s"], help: "Send new and edited cards to Anki", group: "Anki" },
  { command: "export", keys: ["Shift+e"], help: "Export cards as an Anki import file (.txt)", group: "Anki" },
  { command: "open", keys: ["o"], help: "Open a PDF, PPTX or DOCX", group: "App" },
  { command: "help", keys: ["?"], help: "Show shortcuts", group: "App" },
];

export type KeyLike = { key: string; ctrlKey?: boolean; metaKey?: boolean; altKey?: boolean; shiftKey?: boolean };

function matches(spec: string, e: KeyLike): boolean {
  const parts = spec.split("+");
  const key = parts.length > 1 && parts[parts.length - 1] === "" ? "+" : parts[parts.length - 1];
  const mods = new Set(parts.slice(0, -1).map((m) => m.toLowerCase()));
  if (!!(e.ctrlKey || e.metaKey) !== mods.has("ctrl")) return false;
  if (!!e.altKey !== mods.has("alt")) return false;
  if (/^[a-z]$/i.test(key)) return e.key.toLowerCase() === key.toLowerCase() && !!e.shiftKey === mods.has("shift");
  return e.key === key; // symbols and named keys: Shift is part of how the symbol is typed
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
