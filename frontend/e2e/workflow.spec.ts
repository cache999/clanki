import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const FIXTURE = new URL("../../tests/fixtures/vision_test.pdf", import.meta.url).pathname;
const ANKI = "http://127.0.0.1:18765/";

/** Drag-select from the start of one text-layer line to the end of another. */
async function select(page: Page, from: string, to = from) {
  const a = page.locator(".textLayer span", { hasText: from }).first();
  const b = page.locator(".textLayer span", { hasText: to }).first();
  await a.waitFor();
  const ba = (await a.boundingBox())!;
  const bb = (await b.boundingBox())!;
  await page.mouse.move(ba.x + 1, ba.y + ba.height / 2);
  await page.mouse.down();
  await page.mouse.move(bb.x + bb.width - 1, bb.y + bb.height / 2, { steps: 8 });
  await page.mouse.up();
}

const card = (page: Page, text: string) => page.locator(".card", { hasText: text });

test("read, card, send, edit, export", async ({ page, request }) => {
  await page.goto("/");
  await expect(page.locator(".welcome")).toContainText("Open lecture slides");

  // open a document
  await page.locator('input[type="file"]').setInputFiles(FIXTURE);
  await expect(page.locator(".textLayer span", { hasText: "Rhodopsin" })).toBeVisible();
  await expect(page.locator(".reader-bar")).toContainText("p. 1/2");

  // highlight -> Q/A card; Back is prefilled with the selection
  await select(page, "Rhodopsin absorbs");
  await expect(page.locator(".sel-info")).toContainText("Selected on p.1");
  await page.keyboard.press("n");
  await expect(page.locator('textarea[name="back"]')).toHaveValue("Rhodopsin absorbs maximally near 498 nm.");
  await expect(page.locator('textarea[name="front"]')).toBeFocused();
  await page.keyboard.type("Rhodopsin peak absorption (value + unit)");
  await page.locator('textarea[name="back"]').fill("~498 nm");
  await page.keyboard.press("Control+Enter");
  const rho = card(page, "Rhodopsin peak absorption");
  await expect(rho).toContainText("p.1");
  await expect(rho.locator(".status")).toHaveText("new");
  await expect(page.locator(".clanki-hl .hl.has-cards")).toHaveCount(1);
  // the highlight sits on the text it was made from (it is the selection's line box, which can be a
  // little taller than the text span, so compare centres and edges rather than exact boxes)
  const span = (await page.locator(".textLayer span", { hasText: "Rhodopsin absorbs" }).first().boundingBox())!;
  const hl = (await page.locator(".clanki-hl .hl.has-cards").boundingBox())!;
  expect(Math.abs(hl.x - span.x)).toBeLessThan(2);
  expect(Math.abs(hl.x + hl.width - (span.x + span.width))).toBeLessThan(2);
  expect(Math.abs(hl.y + hl.height / 2 - (span.y + span.height / 2))).toBeLessThan(2);
  expect(hl.y).toBeLessThanOrEqual(span.y + 1);
  expect(hl.y + hl.height).toBeGreaterThanOrEqual(span.y + span.height - 1);

  // R: reverse card asks for the reverse prompt
  await page.keyboard.press("r");
  await expect(page.locator('input[name="reverse_prompt"]')).toBeFocused();
  await page.keyboard.type("visual pigment with this peak?");
  await page.keyboard.press("Control+Enter");
  await expect(rho).toContainText("(r: visual pigment with this peak?)");
  await expect(rho).toContainText("Q/A ⇄");

  // three selected lines -> list card, one item per line, bullets stripped
  await page.keyboard.press("]");
  await expect(page.locator(".reader-bar")).toContainText("p. 2/2");
  await select(page, "Photoreceptors", "Ganglion cells");
  await page.keyboard.press("l");
  await expect(page.locator('textarea[name="items"]')).toHaveValue("Photoreceptors\nBipolar cells\nGanglion cells");
  await page.keyboard.type("Retinal cell layers (outer to inner)");
  await page.keyboard.press("Control+Enter");
  await expect(card(page, "List · 3")).toContainText("p.2");

  // a blank card with an error is kept back from Anki
  await page.keyboard.press("n");
  await page.keyboard.type("Card without an answer");
  await page.keyboard.press("Control+Enter");
  await expect(card(page, "Card without an answer")).toContainText("Back is empty");

  // send
  await page.keyboard.press("s");
  await expect(page.locator(".toast")).toContainText("2 added");
  await expect(page.locator(".toast")).toContainText("1 not sent");
  await expect(rho.locator(".status")).toHaveText("sent");
  let inAnki = Object.values(await (await request.get(ANKI)).json()) as { fields: Record<string, string> }[];
  expect(inAnki.map((n) => n.fields.Front ?? n.fields.Title).sort()).toEqual([
    "Retinal cell layers (outer to inner)",
    "Rhodopsin peak absorption (value + unit)",
  ]);
  expect(inAnki.find((n) => n.fields.Front)!.fields.Back).toBe("~498 nm<br>(r: visual pigment with this peak?)");

  // edit a sent card -> edited -> send updates it in Anki
  await rho.click();
  await page.keyboard.press("e");
  await page.locator('textarea[name="back"]').fill("~498 nm (blue-green)");
  await page.keyboard.press("Control+Enter");
  await expect(rho.locator(".status")).toHaveText("edited");
  await page.keyboard.press("s");
  await expect(page.locator(".toast")).toContainText("1 updated");
  inAnki = Object.values(await (await request.get(ANKI)).json()) as { fields: Record<string, string> }[];
  expect(inAnki.find((n) => n.fields.Front)!.fields.Back).toBe("~498 nm (blue-green)<br>(r: visual pigment with this peak?)");

  // delete and undo
  await card(page, "Card without an answer").click();
  await page.keyboard.press("x");
  await expect(card(page, "Card without an answer")).toHaveCount(0);
  await page.keyboard.press("z");
  await expect(card(page, "Card without an answer")).toHaveCount(1);

  // export
  const [download] = await Promise.all([page.waitForEvent("download"), page.keyboard.press("Shift+E")]);
  expect(download.suggestedFilename()).toBe("vision_test_anki.txt");
  const text = readFileSync((await download.path())!, "utf-8");
  expect(text.split("\n")[2]).toBe("#guid column:1");
  expect(text).toContain("~498 nm (blue-green)<br>(r: visual pigment with this peak?)");

  // help
  await page.keyboard.press("?");
  await expect(page.getByRole("dialog", { name: "Keyboard shortcuts" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("document survives a reload with its highlights", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".textLayer span", { hasText: "Rhodopsin" })).toBeVisible();
  await expect(page.locator(".card")).toHaveCount(3);
  await expect(page.locator(".clanki-hl .hl.has-cards").first()).toBeVisible();
});

test("generate cards with the LLM", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".textLayer span", { hasText: "Rhodopsin" })).toBeVisible();

  // no key yet: the banner points to Settings; save and test a key there
  await expect(page.locator(".banner")).toContainText("No DeepSeek API key");
  await page.keyboard.press(",");
  const settings = page.getByRole("dialog", { name: "Settings" });
  await expect(settings.locator(".key-status")).toContainText("not set");
  await settings.locator('input[type="password"]').fill("sk-test-abcd");
  await settings.getByRole("button", { name: "Save" }).click();
  await expect(settings.locator(".key-status")).toContainText("credential store (…abcd)");
  await settings.getByRole("button", { name: "Test" }).click();
  await expect(settings).toContainText("The key works");
  await page.keyboard.press("Escape");
  await expect(settings).toHaveCount(0);
  await expect(page.locator(".banner")).toHaveCount(0);

  // G on a selection, with a focus; its highlight turns green once it has cards
  const greenBefore = await page.locator(".clanki-hl .hl.has-cards").count();
  await select(page, "Cones mediate colour vision");
  await page.keyboard.press("g");
  const focus = page.locator(".focusbox input");
  await expect(focus).toBeFocused();
  await focus.fill("function");
  await page.keyboard.press("Enter");
  const gen = card(page, "Generated: Cones mediate colour vision in bright");
  await expect(gen).toContainText("focus was function");
  await expect(gen.locator(".ai")).toHaveText("AI");
  await expect(gen.locator(".kindtag")).toHaveText("fact");
  await expect(page.locator(".clanki-hl .hl.has-cards")).toHaveCount(greenBefore + 1);

  // jobs panel: cost, and carding left-out content
  await page.keyboard.press(".");
  const panel = page.getByRole("dialog", { name: "Generation jobs" });
  await expect(panel.locator(".job").first()).toContainText("done");
  await expect(panel.locator(".job").first()).toContainText("1 cards");
  await panel.locator("summary").first().click();
  await panel.getByRole("button", { name: "Card this" }).first().click();
  await expect(card(page, "Generated: a left-out sentence")).toHaveCount(1);
  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);

  // whole document, after the estimate
  await page.keyboard.press("Shift+G");
  const confirm = page.getByRole("dialog", { name: "Generate whole document" });
  await expect(confirm).toContainText("1 section");
  await expect(confirm).toContainText("deepseek-flash");
  await page.keyboard.press("Enter");
  const listCard = card(page, "Generated list");
  await expect(listCard).toContainText("p.1–2");
  await expect(listCard.locator(".issues .warning")).toContainText("check the order");
  // model notes can be dismissed; the card's status is unaffected
  await listCard.locator(".issues .dismiss").click();
  await expect(listCard.locator(".issues")).toHaveCount(0);
  await expect(listCard.locator(".status")).toHaveText("new");

  // model choice persists
  await page.locator("select.model").selectOption("deepseek-v4-pro");
  await page.reload();
  await expect(page.locator("select.model")).toHaveValue("deepseek-v4-pro");
});
