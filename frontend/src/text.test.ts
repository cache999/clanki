import { describe, expect, it } from "vitest";
import { parseTags, richHtml } from "./text";

describe("richHtml", () => {
  it("keeps the inline tags Anki export allows and escapes everything else", () => {
    expect(richHtml('<b>Prodrug</b> HCO<sub>3</sub><sup>-</sup> <img src=x onerror="alert(1)">')).toBe(
      "<b>Prodrug</b> HCO<sub>3</sub><sup>-</sup> &lt;img src=x onerror=&quot;alert(1)&quot;&gt;",
    );
  });

  it("drops attributes by never restoring tags that carry them", () => {
    expect(richHtml('<b onclick="x">y</b>')).toBe("&lt;b onclick=&quot;x&quot;&gt;y</b>");
  });

  it("turns newlines into line breaks", () => {
    expect(richHtml("a\nb<br>c")).toBe("a<br>b<br>c");
  });
});

describe("parseTags", () => {
  it("splits on whitespace and commas, dropping duplicates", () => {
    expect(parseTags(" NHB::vision, kind::fact  NHB::vision ")).toEqual(["NHB::vision", "kind::fact"]);
  });
});

describe("card images", () => {
  it("shows clanki's screenshots and escapes any other image", () => {
    const name = "clanki-0123456789abcdef0123456789abcdef.png";
    expect(richHtml(`~498 nm\n<img src="${name}">`)).toBe(`~498 nm<br><img class="card-img" src="/api/media/${name}">`);
    expect(richHtml('<img src="http://x.example/a.png">')).toBe("&lt;img src=&quot;http://x.example/a.png&quot;&gt;");
  });
});
