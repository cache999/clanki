import { describe, expect, it } from "vitest";
import { clozeCount, clozeHtml, clozeTitle, wrapCloze } from "./cloze";

describe("wrapCloze", () => {
  it("clozes the selection with the next number, like Anki's Ctrl+Shift+C", () => {
    const t = "Fatigue: resistant vs prone";
    expect(wrapCloze(t, 9, 27, false)).toEqual({ text: "Fatigue: {{c1::resistant vs prone}}", cursor: 35 });
    expect(wrapCloze("{{c1::a}} {{c2::b}} c", 20, 21, false).text).toBe("{{c1::a}} {{c2::b}} {{c3::c}}");
  });

  it("reuses the highest number with Alt, so the answers show together", () => {
    expect(wrapCloze("{{c1::a}} {{c2::b}} c", 20, 21, true).text).toBe("{{c1::a}} {{c2::b}} {{c2::c}}");
    expect(wrapCloze("x", 0, 1, true).text).toBe("{{c1::x}}");
  });

  it("with nothing selected, leaves the cursor inside an empty cloze", () => {
    expect(wrapCloze("Fatigue: ", 9, 9, false)).toEqual({ text: "Fatigue: {{c1::}}", cursor: 15 });
  });
});

describe("clozeCount", () => {
  it("counts the cards Anki makes: one per number", () => {
    expect(clozeCount("{{c1::a}} {{c1::b}} {{c3::c::hint}}")).toBe(2);
    expect(clozeCount("no clozes")).toBe(0);
  });
});

describe("clozeHtml", () => {
  it("marks each answer with its number, hints left out", () => {
    expect(clozeHtml("Fatigue: {{c1::resistant vs prone}}<br>Cause: {{c2::fibre type::type?}}")).toBe(
      'Fatigue: <span class="cloze" data-c="1">resistant vs prone</span><br>' +
        'Cause: <span class="cloze" data-c="2">fibre type</span>',
    );
  });
});

describe("clozeTitle", () => {
  it("is the first line, answers shown", () => {
    expect(clozeTitle("Motor units\n\nFatigue: {{c1::resistant}}")).toBe("Motor units");
    expect(clozeTitle("Mast cells make {{c1::leukotrienes}} [2]")).toBe("Mast cells make leukotrienes [2]");
  });
});
