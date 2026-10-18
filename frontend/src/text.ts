// Card text helpers. Mirrors clanki.anki_format.rich: only bare b/i/u/sub/sup/br survive, and
// clanki's own screenshots (media.TAG), shown from clanki's server.

const INLINE = /&lt;(\/?(?:b|i|u|sub|sup)|br\s*\/?)&gt;/gi;
const IMAGE = /&lt;img src=&quot;(clanki-[0-9a-f]{32}\.(?:png|jpg|gif|webp))&quot;&gt;/g;

export function richHtml(s: string): string {
  const escaped = s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  return escaped
    .replace(INLINE, (_m, tag: string) => `<${tag}>`)
    .replace(IMAGE, (_m, name: string) => `<img class="card-img" src="/api/media/${name}">`)
    .replace(/\r?\n/g, "<br>");
}

export function parseTags(s: string): string[] {
  return [...new Set(s.split(/[\s,]+/).filter(Boolean))];
}
