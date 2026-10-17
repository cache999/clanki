// Card text helpers. Mirrors clanki.anki_format.rich: only bare b/i/u/sub/sup/br survive.

const INLINE = /&lt;(\/?(?:b|i|u|sub|sup)|br\s*\/?)&gt;/gi;

export function richHtml(s: string): string {
  const escaped = s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  return escaped.replace(INLINE, (_m, tag: string) => `<${tag}>`).replace(/\r?\n/g, "<br>");
}

export function parseTags(s: string): string[] {
  return [...new Set(s.split(/[\s,]+/).filter(Boolean))];
}
