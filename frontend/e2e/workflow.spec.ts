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

  // export: Shift+E shows what will be exported; Enter downloads it
  await page.keyboard.press("Shift+E");
  const dialog = page.getByRole("dialog", { name: "Export" });
  await expect(dialog.locator(".export-count")).toHaveText("0 cards · 1 with errors left out (fix them first)");
  await dialog.getByLabel("All cards").check(); // the rest are already in Anki
  await expect(dialog.locator(".export-count")).toContainText(/[1-9] cards/);
  await dialog.getByLabel("Mark them exported").uncheck();
  const [download] = await Promise.all([page.waitForEvent("download"), page.keyboard.press("Enter")]);
  expect(download.suggestedFilename()).toBe("vision_test_anki.txt");
  await expect(page.locator(".toast")).toContainText("Exported");
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
  await settings.getByRole("button", { name: "Save", exact: true }).click();
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

  // the first time, a notice says what is sent to a third party; Cancel sends nothing
  const notice = page.getByRole("dialog", { name: "Before using the AI features" });
  await expect(notice).toContainText("DeepSeek");
  await expect(notice).toContainText("right to share");
  await notice.getByRole("button", { name: "Cancel" }).click();
  await expect(notice).toHaveCount(0);
  await expect(page.locator(".clanki-hl .hl.has-cards")).toHaveCount(greenBefore);
  await page.keyboard.press("g");
  await page.locator(".focusbox input").fill("function");
  await page.keyboard.press("Enter");
  await notice.getByRole("button", { name: "I understand, continue" }).click();
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

test("ask the AI to change a card, then accept or discard", async ({ page }) => {
  await page.goto("/");
  const rho = card(page, "Rhodopsin peak absorption");
  await rho.click();
  await expect(rho.locator(".status")).toHaveText("sent");

  // A: say what to change; the suggestion shows the change and waits
  await page.keyboard.press("a");
  const ask = rho.locator(".askbox input");
  await expect(ask).toBeFocused();
  await ask.fill("shorter front");
  await page.keyboard.press("Enter");
  const suggestion = rho.locator(".suggest");
  await expect(suggestion).toContainText("AI suggestion for “shorter front”");
  await expect(suggestion.locator("del")).toHaveText("Rhodopsin peak absorption (value + unit)");
  await expect(suggestion.locator("ins")).toHaveText("Edited: shorter front");
  await expect(rho.locator(".front")).toHaveText("Rhodopsin peak absorption (value + unit)");

  // Y accepts: the card changes, and since it is in Anki it is marked for update
  await page.keyboard.press("y");
  const edited = card(page, "Edited: shorter front");
  await expect(edited.locator(".suggest")).toHaveCount(0);
  await expect(edited.locator(".status")).toHaveText("edited");

  // a split suggestion can be discarded with D
  await edited.click();
  await page.keyboard.press("a");
  await edited.locator(".askbox input").fill("split into two");
  await page.keyboard.press("Enter");
  await expect(edited.locator(".suggest")).toContainText("splits into 2 cards");
  await expect(edited.locator(".newcard")).toContainText("Second card");
  await page.keyboard.press("d");
  await expect(edited.locator(".suggest")).toHaveCount(0);
  await expect(card(page, "Second card")).toHaveCount(0);
  await expect(edited.locator(".front")).toHaveText("Edited: shorter front");
});

test("coverage strip, and warnings for cards already in Anki", async ({ page, request }) => {
  // a card made in Anki itself
  const note = { deckName: "Default", modelName: "Basic (optional reversed card)", tags: [],
    fields: { Front: "Bipolar cells (function)", Back: "relay photoreceptor signals", "Add Reverse": "", Why: "" } };
  await request.post(ANKI, { data: { action: "addNotes", version: 6, params: { notes: [note] } } });
  await page.goto("/");

  // the strip has a segment per page; clicking one goes there
  const segs = page.locator(".coverage .seg");
  await expect(segs).toHaveCount(2);
  await expect(segs.nth(0)).toHaveClass(/carded/);
  await segs.nth(1).click();
  await expect(page.locator(".reader-bar")).toContainText("p. 2/2");
  await segs.nth(0).click();
  await expect(page.locator(".reader-bar")).toContainText("p. 1/2");

  // Settings re-reads Anki and shows the subquestion vocabulary
  await page.keyboard.press(",");
  const dialog = page.getByRole("dialog", { name: "Settings" });
  await dialog.getByRole("button", { name: "Re-read Anki" }).click();
  await expect(dialog).toContainText(/\d+ cards read from Anki/);
  await expect(dialog.locator(".facets")).toContainText("MoA");
  await page.keyboard.press("Escape");

  // a new card on the same question gets a warning showing the Anki card
  await segs.nth(1).click();
  await select(page, "Bipolar cells");
  await page.keyboard.press("n");
  await page.keyboard.type("Bipolar cells (function)");
  await page.keyboard.press("Control+Enter");
  const bip = card(page, "Bipolar cells (function)");
  await expect(bip.locator(".issues")).toContainText('Already in Anki: "Bipolar cells (function)" → relay photoreceptor signals (Default)');
  await expect(segs.nth(1)).toHaveAttribute("title", /p\.2: \d+ cards/);
});

test("screenshots: capture, pick one or several, read them, and drop one onto a card", async ({ page }) => {
  await page.goto("/");
  await page.locator(".textLayer span").first().waitFor();

  // I, then drag a box: the screenshot is kept and picked, and nothing is sent yet
  await page.keyboard.press("i");
  await expect(page.locator(".reader-bar")).toContainText("Drag a box");
  const box = (await page.locator(".page").first().boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.1, box.y + box.height * 0.5);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.8, { steps: 6 });
  await page.mouse.up();
  const shots = page.locator(".tray .shot");
  await expect(shots).toHaveCount(1);
  await expect(shots.first()).toHaveClass(/picked/);
  await expect(page.locator(".clanki-hl .hl.region.picked")).toHaveCount(1);
  await expect(page.locator(".snippet")).toHaveCount(0);

  // T reads the picked screenshot; the transcript opens for correcting
  await page.keyboard.press("t");
  const snippet = page.locator(".snippet textarea");
  await expect(snippet).toHaveValue(/Median nerve: carpal tunnel/);
  await expect(snippet).toBeFocused();
  await snippet.fill("Median nerve: carpal tunnel\nUlnar nerve: Guyon's canal");
  await page.keyboard.press("Control+Enter");
  await expect(page.locator(".sel-info")).toContainText("figure on p.1");
  await page.keyboard.press("g");
  await page.keyboard.press("Enter");
  const made = card(page, "Generated: Median nerve: carpal tunnel");
  await expect(made).toContainText("p.1 figure");

  // a pasted screenshot joins the tray, picked on its own
  const png = readFileSync(new URL("../../tests/fixtures/raas.png", import.meta.url)).toString("base64");
  await page.evaluate((b64) => {
    const dt = new DataTransfer();
    dt.items.add(new File([Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))], "shot.png", { type: "image/png" }));
    document.body.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true }));
  }, png);
  await expect(shots).toHaveCount(2);
  await expect(page.locator(".tray .shot.picked")).toHaveCount(1);

  // Shift+click the box on the page picks both; T joins their transcripts, labelled
  await page.locator(".clanki-hl .hl.region").first().scrollIntoViewIfNeeded();
  const region = (await page.locator(".clanki-hl .hl.region").first().boundingBox())!;
  await page.keyboard.down("Shift");
  await page.mouse.click(region.x + 20, region.y + 20);
  await page.keyboard.up("Shift");
  await expect(page.locator(".tray .shot.picked")).toHaveCount(2);
  await page.keyboard.press("t");
  await expect(snippet).toHaveValue(/\[Image 1, p\.1\][\s\S]*\[Image 2, p\.1\][\s\S]*Guyon's canal/);
  await page.keyboard.press("Escape");
  await expect(page.locator(".snippet")).toHaveCount(0);

  // drag a screenshot onto a card: its fields appear as drop targets
  await shots.first().hover();
  await page.mouse.down();
  await made.hover();
  await made.locator(".dropzone", { hasText: "Back" }).hover();
  await page.mouse.up();
  await expect(made.locator(".back img.card-img")).toHaveCount(1);
});

test("open a web page by its address", async ({ page }) => {
  await page.goto("/");
  await page.locator(".textLayer span").first().waitFor();
  page.once("dialog", (d) => void d.accept(ANKI + "article"));
  await page.keyboard.press("Shift+O");
  await expect(page.locator(".textLayer span", { hasText: "carpal tunnel" }).first()).toBeVisible();
  await expect(page.locator("header select").first()).toHaveValue(/.+/);
  await expect(page.locator("header select option:checked").first()).toHaveText("The Median Nerve");
});

test("undo and redo any change, and undo back through the history", async ({ page, request }) => {
  // a card of its own, in the document the app opens (the newest)
  const docs = await (await request.get("/api/documents")).json();
  const docId = docs[docs.length - 1].id;
  await request.post(`/api/documents/${docId}/notes`, { data: { type: "qa", front: "Undo test card", back: "original back" } });
  await page.goto("/");
  const rho = card(page, "Undo test card");
  await rho.click();
  const before = "original back";

  // edit the Back, then Z undoes it and Shift+Z redoes it
  await page.keyboard.press("e");
  await page.locator('textarea[name="back"]').fill("498 nm (undo test)");
  await page.keyboard.press("Control+Enter");
  await expect(rho.locator(".back")).toHaveText("498 nm (undo test)");
  await page.keyboard.press("z");
  await expect(page.locator(".toast")).toContainText("Undid: Edit card");
  await expect(rho.locator(".back")).toHaveText(before);
  await page.keyboard.press("Shift+Z");
  await expect(page.locator(".toast")).toContainText("Redid: Edit card");
  await expect(rho.locator(".back")).toHaveText("498 nm (undo test)");

  // H lists the changes; clicking one undoes back to it
  await page.keyboard.press("h");
  const rows = page.locator(".history li");
  await expect(rows.first()).toContainText("Edit card");
  await rows.first().click();
  await expect(rho.locator(".back")).toHaveText(before);
  await expect(rows.first()).toHaveClass(/undone/);
  await page.keyboard.press("Escape");
  await expect(page.locator(".history")).toHaveCount(0);
});

test("exported cards are marked, and Send to Anki skips them", async ({ page, request }) => {
  const docs = await (await request.get("/api/documents")).json();
  const docId = docs[docs.length - 1].id;
  await request.post(`/api/documents/${docId}/notes`, { data: { type: "qa", front: "Export test card", back: "exported" } });
  await page.goto("/");
  const c = card(page, "Export test card");
  await expect(c.locator(".status")).toHaveText("new");

  await page.keyboard.press("Shift+E");
  const dialog = page.getByRole("dialog", { name: "Export" });
  await dialog.getByPlaceholder("only this tag").fill("nonexistent-tag");
  await expect(dialog.locator(".export-count")).toHaveText("0 cards");
  await dialog.getByPlaceholder("only this tag").fill("");
  await expect(dialog.locator(".export-count")).toContainText(/[1-9]\d* cards?/);
  await Promise.all([page.waitForEvent("download"), dialog.getByRole("button", { name: "Export" }).click()]);
  await expect(page.locator(".toast")).toContainText("marked exported");
  await expect(c.locator(".status")).toHaveText("exported");

  await page.keyboard.press("s");
  await expect(page.locator(".toast")).toContainText("already up to date");
  await expect(c.locator(".status")).toHaveText("exported");
});

test("settings: defaults for new documents, and this computer's settings", async ({ page }) => {
  await page.goto("/");
  await page.locator(".textLayer span").first().waitFor();
  await page.keyboard.press(",");
  const dialog = page.getByRole("dialog", { name: "Settings" });
  const defaults = dialog.locator(".defaults");
  await defaults.getByLabel("Tags").fill("e2e-default year2");
  await defaults.getByRole("button", { name: "Save defaults" }).click();
  await expect(dialog).toContainText("Defaults saved");
  // this e2e server runs without a config file, so this PC's settings are shown but not editable
  const address = dialog.locator(".machine").getByLabel("Anki address");
  await expect(address).toHaveValue("http://127.0.0.1:18765");
  await expect(address).toBeDisabled();
  await page.keyboard.press("Escape");

  await page.locator('input[type="file"]').setInputFiles(FIXTURE);
  await expect(page.locator(".textLayer span", { hasText: "Rhodopsin" }).first()).toBeVisible();
  await expect(page.locator(".docfield", { hasText: "Tags" }).locator("input")).toHaveValue("e2e-default year2");
});

test("each document has a profile, and MathJax on cards is rendered", async ({ page, request }) => {
  const docs = await (await request.get("/api/documents")).json();
  const docId = docs[docs.length - 1].id;
  await request.post(`/api/documents/${docId}/notes`, {
    data: { type: "qa", front: "Transformer attention (formula)", back: "\\(\\mathrm{softmax}(QK^\\top/\\sqrt{d_k})V\\)" },
  });
  await page.goto("/");
  const profile = page.locator(".docfield", { hasText: "Profile" }).locator("select");
  await profile.selectOption({ label: "Machine learning (papers)" });
  await expect(card(page, "Transformer attention").locator(".back .katex")).toHaveCount(1);
  await page.reload();
  await expect(profile).toHaveValue("ml_papers");
});

test("cards from your own prompt, without the document", async ({ page }) => {
  await page.goto("/");
  await page.locator(".textLayer span").first().waitFor();
  await page.keyboard.press("p");
  const box = page.locator(".promptbox input");
  await expect(box).toBeFocused();
  await box.fill("Frank-Starling law");
  await page.keyboard.press("Enter");
  const made = card(page, "Prompted: Frank-Starling law");
  await expect(made).toContainText("own");
  await expect(page.locator(".promptbox")).toHaveCount(0);
});
