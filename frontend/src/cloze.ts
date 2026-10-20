// Cloze cards (Anki's own Cloze note type): the answers are marked {{c1::answer}} or
// {{c1::answer::hint}} in the text. Mirrors clanki.anki_format.CLOZE_DELETION.

const DELETION = /\{\{c(\d+)::([\s\S]*?)(?:::([\s\S]*?))?\}\}/g;

function numbers(text: string): number[] {
  return [...text.matchAll(DELETION)].map((m) => Number(m[1]));
}

/** The text with [start, end) clozed, as Anki's Ctrl+Shift+C does (the next number) or, with
 * `same`, Ctrl+Shift+Alt+C (the highest number so far, so the answers show on one card). The
 * cursor goes after the cloze, or inside it if nothing was selected. */
export function wrapCloze(text: string, start: number, end: number, same: boolean): { text: string; cursor: number } {
  const ns = numbers(text);
  const top = ns.length ? Math.max(...ns) : 0;
  const open = `{{c${same ? Math.max(top, 1) : top + 1}::`;
  const inner = text.slice(start, end);
  return {
    text: text.slice(0, start) + open + inner + "}}" + text.slice(end),
    cursor: start + open.length + (inner ? inner.length + 2 : 0),
  };
}

/** How many cards Anki makes from the text: one per cloze number. */
export function clozeCount(text: string): number {
  return new Set(numbers(text)).size;
}

/** Card HTML with each answer marked (and numbered by CSS), hints left out. */
export function clozeHtml(html: string): string {
  return html.replace(DELETION, (_m, n: string, answer: string) => `<span class="cloze" data-c="${n}">${answer}</span>`);
}

/** The first line with its answers shown: the cloze's title, or its sentence. */
export function clozeTitle(text: string): string {
  return text.replace(DELETION, (_m, _n, answer: string) => answer).trim().split(/\r?\n/)[0];
}
