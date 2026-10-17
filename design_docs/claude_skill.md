# Anki cards

Turn source text into atomic, reversible Q/A cards and overlapping-cloze list cards for the user's two note types, and return a tab-separated Anki import file. One pass replaces the old router → generator → reviewer → editor pipeline: plan, write, self-review, build.

## Note types (the user's set-up)

| Note type (exact name) | Fields, in order | Used for |
|---|---|---|
| `Basic (and reversed card)` | Front, Back, Why | every Q/A card; each note makes two cards, Front→Back and Back→Front |
| `Cloze (overlapping)` (Cloze Overlapper add-on) | Original, Title, Remarks, Sources, Settings, Text1–Text20, Full | ordered processes and unordered sets |

- Why is the user's own addition to the stock note type, shown on both answer sides by `{{#Why}}<hr><div class=why>{{Why}}</div>{{/Why}}` in each back template. If imported cards arrive without explanations, the field is missing: Anki silently drops columns beyond a note type's fields. One-time set-up, if the user has not done it: Tools ▸ Manage Note Types ▸ Basic (and reversed card) ▸ Fields ▸ Add "Why" (third), then Cards ▸ append the snippet to the back template of both Card 1 and Card 2. Adding a field forces one full sync.
- The builder fills every overlapper field exactly as the add-on's own generator would, so imported list notes are complete without opening the editor. The add-on need not run; its note type must exist with the default field names and order.
- If the user's names or field order differ, edit the constants and field lists in the script to match.

## Scope

- Default: card everything testable in the source. If the user narrows it ("UKMLA-relevant only", "high-yield", one section), follow that and list what was left out in the summary.
- Front and Back carry only what the source states. The Why may draw on general knowledge to explain it.
- If the source is wrong, imprecise or out of date against current UK guidance, card the correct version only when certain, and flag every such change in the summary. Otherwise card the source as written and flag the doubt.

## Workflow

1. Read the whole source before writing. Note the few principles that generate most of its facts; the Why fields will reuse them.
2. Walk the source sentence by sentence and assign each testable fact to a card (types below). One fact may feed more than one card.
3. Write the cards and their Why fields to the rules below.
4. Self-review against the checklist and rewrite failures silently.
5. Build the import file with the script and return the output described under "Output".

## Card types

| Kind | Use for | Note type | Tag |
|---|---|---|---|
| Fact | a name, definition, location, value, drug of choice | Basic (and reversed card) | `kind::fact` |
| Linkage | a relation between two things: cause→effect, structure→function, drug→receptor, finding→differential | Basic (and reversed card) | `kind::linkage` |
| Concept | why or how something happens | Basic (and reversed card) | `kind::concept` |
| Process | ordered steps, 4 or more | Cloze (overlapping), ordered | `kind::process` |
| Set | unordered members, 4 or more (causes, features, adverse effects) | Cloze (overlapping), unordered | `kind::set` |

- A set or sequence of 3 items or fewer is a Basic card whose Back lists them, separated by semicolons.
- Figures, diagrams and images are not carded. List them in the summary as candidates for Anki's built-in Image Occlusion.

## The prompt (Front, or a list's Title)

- **Atomic.** One question, one answer. Two facts only when tightly bound, such as a nerve's origin and destination.
- **Unambiguous.** Exactly one correct answer. Name the dimension wanted: location, function, mechanism, value with units. "Describe X" is too open; ask for the specific attribute.
- **Context-free.** Answerable cold months later: name the organ, system, condition or drug. No "this", "the above", figure or section references.
- **No yes/no or true/false.** "Is X true? Why?" becomes "Why X?".
- **No giveaways.** Keep answer words and grammatical cues out of the prompt.
- **Short.** Keep only context that disambiguates. Telegraphic noun phrases are fine: "Nephron segment that reabsorbs most filtered HCO₃⁻".
- **Interference.** Where two items are easily confused (two drugs, two cell types), add a card that discriminates between them.
- **Direction.** For clinical findings, prefer finding → what to think of, the direction exams test (P(diagnosis | finding), not P(finding | diagnosis)). The reverse card supplies the other direction.

## The answer (Back)

- A phrase, ideally 15 words or fewer. Explanation belongs in Why, never in Back.
- **Reversible.** Every Basic note also makes a Back→Front card, so the Back must point back to its Front: specific, not generic. "Net production: it adds new HCO₃⁻ to plasma", not "The kidney". No two notes may share a Back; the builder warns if they do.
- Values carry SI units (mmol/L) and UK reference conventions.

## Lists (Title + items)

- The Title is the prompt. It says what the list is and, for a process, that order matters.
- Each item stands alone (readable without its neighbours), is concise, and contains no `::`, `{{` or `}}`.
- 2 to 20 items; split anything over about 8. Split by generating principle where one exists: adverse effects from principle 1 and from principle 2 make two lists that each cohere.
- The whole-list card is on by default only for ordered lists of 5 items or fewer, because recalling a long or unordered list whole is a classic leech. Override with `"full": true` or `false`.

## The Why field

Most cards get one. It is read after answering, and its job is to make the fact derivable rather than arbitrary. It follows the UKMLA reasoning standard:

- 1–3 sentences, about 50 words at most. Do not restate the answer, and do not add new testable facts; give those their own card.
- **Reason from physiology first.** Where a physical or quantitative principle explains the fact cleanly, use it: Poiseuille, Laplace, Starling forces, Fick, mass balance, feedback control. The user has an engineering background.
- **Smallest principle, one causal step.** State the principle and show the step from it to this fact. Cards from one source usually share one or two principles; word them the same way each time so the cards reinforce each other.
- **Never invent a mechanism.** If no principle generates the fact (an eponym, a convention, an empirical association), leave Why empty for bare names and definitions, or write "No mechanism; memorise." with where the fact comes from.
- **Convention versus mechanism.** Where the answer rests on guideline convention, say so and name it (NICE, NICE CKS, SIGN, BTS, Resuscitation Council UK, BNF). If unsure of a current threshold or dose, say so in the Why and flag it in the summary. Never guess.
- **No post-hoc explanation of clinical features.** Explain a sign by its site or the disturbance it reflects, and say what else causes it. Write "Stridor: turbulent flow through a narrowed extrathoracic airway; croup is commonest in toddlers, but consider foreign body and epiglottitis", not "stridor, due to subglottic oedema in croup".
- **Mnemonic** only if it is genuinely memorable and maps cleanly; append "Mnemonic: …". Mostly for sets.
- Pitch to the depth of the source. For clinical material, use UKMLA level and current UK guidance, UK terminology, units and drug names.

## Self-review checklist

Check every card and rewrite failures; do not output a verdict.

- One question, one short answer; unambiguous; readable without the source.
- The reverse card is answerable, and no Back is shared.
- Sets and sequences longer than 3 are lists; 3 or fewer are Basic cards.
- Every list item stands alone.
- Every testable fact in the source is on a card, or deliberately out of the user's scope.
- No invented mechanism; uncertain guideline details flagged.
- Formatting rules met.

## Formatting

- Plain text. Use Unicode for chemistry and symbols: HCO₃⁻, Na⁺, CO₂, ≥, →, µ.
- Front, Back and Why accept only `<b> <i> <u> <sub> <sup> <br>`; the builder escapes everything else. Titles and list items are plain text only.
- UK spelling throughout.
- Deck: the user's, if given; otherwise a short hierarchy inferred from the topic (`Physiology::Renal`, `UKMLA::Cardiology`), stated in the summary so it can be changed.
- Tags: a topic hierarchy (`renal::acid-base`), the `kind::` tag, and `ai-generated` on every note, so the batch can be found and audited later.

## Building the file

1. Write the cards as JSON:

```json
{
  "deck": "Physiology::Renal",
  "tags": ["renal::acid-base", "ai-generated"],
  "source": "short source name, shown in the Sources field of list notes",
  "cards": [
    {"type": "qa", "front": "...", "back": "...", "why": "...", "tags": ["kind::concept"]},
    {"type": "list", "title": "...", "ordered": true, "items": ["...", "..."], "why": "...", "tags": ["kind::process"]}
  ]
}
```

   Optional per card: `"deck"`; for lists, `"full"`.
2. If `build_anki_import.py` is not in the working directory, write the script at the end of this file to it. Run `python3 build_anki_import.py cards.json -o <topic>_anki.txt`.
3. Fix every ERROR (those cards were skipped) and act on every WARNING, then rebuild.
4. Without code execution, write the file by hand following "File format".

## Output

1. **Summary**, kept short:
   - One line: notes → cards, deck, tags.
   - A table with one row per note: Kind | Prompt | Answer (for lists: Title | "n items"). Keep cells brief.
   - Flags, if any: source corrections or doubts, uncertain guideline details, Image Occlusion candidates, content left out under the user's scope, builder warnings.
2. **The import file** in a single `text` code block, copied verbatim from the built file, with literal tab characters.
3. When file tools are available, also send the .txt file itself, since some editors turn pasted tabs into spaces.
4. One closing line: save as a UTF-8 .txt and use File ▸ Import; the headers set note types, decks and tags, and re-importing updates notes whose first field matches.

## File format (reference, for writing by hand)

Six header lines, then one note per line: tab-separated, 29 columns on every row. Below, ⇥ stands for a literal tab character.

```
#separator:tab
#html:true
#notetype column:1
#deck column:2
#tags column:3
#columns:Note type⇥Deck⇥Tags⇥F1⇥F2⇥…⇥F26
```

- Columns 1–3: note type, deck, space-separated tags. Columns 4 onwards map to the note type's fields in order; pad with empty columns to 29.
- Basic row: Front, Back, Why, then 23 empty columns.
- Overlapper row: Original, Title, Remarks (the Why), Sources, Settings, Text1–Text20, Full.
  - Original: the list as `<ol><li>…</li></ol>` (ordered) or `<ul><li>…</li></ul>` (unordered).
  - Settings: `1,1,0 | n,n,n,n` for ordered, `all,1,all | n,n,n,n` for unordered; a final `y` instead of `n` means no whole-list card.
  - Text k (k = 1…n): the same list with item k written `{{ck::item}}`. Ordered: item k−1 shown in full and every other item `...`. Unordered: every other item shown in full. Text n+1 to Text20 empty.
  - Full: every item written `{{c21::item}}`, or empty when there is no whole-list card.
- Escape `&`, `<`, `>`, `"` as `&amp;`, `&lt;`, `&gt;`, `&quot;`; write newlines as `<br>`; never put a tab inside a field.
- The first field is Anki's duplicate key: no two notes of one type may share it.

## Worked example

Source (abridged): the kidney regulates HCO₃⁻ and, on a normal diet, is a net producer of it, "because HCO₃⁻ production is required to buffer urine pH". Net production requires four steps. Most filtered HCO₃⁻ is reabsorbed in the proximal tubule. In alkalosis reabsorption falls and type B intercalated cells secrete HCO₃⁻. In every segment, HCO₃⁻ is reabsorbed by a cycle of H⁺ secretion, luminal CO₂ formation, CO₂ entry and intracellular regeneration.

Cards:

- Fact. Kidney's net handling of HCO₃⁻ on a normal diet → Net production: it adds new HCO₃⁻ to plasma. Why: each H⁺ secreted and excreted bound to a urinary buffer leaves one new HCO₃⁻ in plasma; HCO₃⁻ is excreted on balance only in alkalosis.
- Concept. Why must the kidney generate new HCO₃⁻ on a normal diet? → To replace plasma HCO₃⁻ consumed in buffering the daily non-volatile acid load. Why: metabolism of dietary protein yields non-volatile acids; plasma HCO₃⁻ buffers them, so without renal regeneration the pool would fall day by day.
- Fact. Nephron segment that reabsorbs most filtered HCO₃⁻ → Proximal tubule (the remainder in later segments). Why: high-capacity apical Na⁺/H⁺ exchange and luminal carbonic anhydrase make H⁺ secretion and luminal CO₂ formation fastest there.
- Fact. Type B intercalated cells: acid–base transport direction → Secrete HCO₃⁻ into the tubular lumen. Why: their polarity is the reverse of type A cells, with apical Cl⁻/HCO₃⁻ exchange (pendrin) and basolateral H⁺-ATPase.
- Linkage. Two renal changes that increase HCO₃⁻ excretion in alkalosis → Less reabsorption of filtered HCO₃⁻; secretion by type B intercalated cells.
- Concept. In HCO₃⁻ reabsorption, why is filtered HCO₃⁻ first converted to CO₂? → HCO₃⁻ cannot cross the apical membrane; CO₂ diffuses freely across it.
- Process (4 items, with whole-list card). Steps required for net renal HCO₃⁻ production.
- Process (6 items, no whole-list card). Mechanism of HCO₃⁻ reabsorption (any nephron segment). Why: net effect is one HCO₃⁻ lost from the lumen and one gained by plasma, with no net H⁺ excreted.

Summary flag: "The source's reason for net production ('to buffer urine pH') was replaced by the standard mechanism, replacing HCO₃⁻ consumed by the daily non-volatile acid load. Check against your course notes."

Built: 6 Basic notes → 12 cards; 2 overlapping-cloze notes → 11 cards.

## Builder script

```python
#!/usr/bin/env python3
"""Build an Anki import file from a card spec (JSON). Usage:
python3 build_anki_import.py cards.json -o cards.txt"""
import argparse, html, json, re, sys

BASIC, OVERLAP = "Basic (and reversed card)", "Cloze (overlapping)"
OLC_MAX, N_FIELDS, FULL_MAX = 20, 26, 5
INLINE = re.compile(r"&lt;(/?(?:b|i|u|sub|sup)|br\s*/?)&gt;", re.I)


def esc(s):
    s = html.escape(str(s or ""), quote=False).replace('"', "&quot;")
    return s.replace("\r\n", "\n").replace("\t", " ").strip().replace("\n", "<br>")


def rich(s):   # Front, Back, Why: a few inline tags allowed
    return INLINE.sub(lambda m: "<" + m.group(1) + ">", esc(s))


def ul(tag, xs):
    return "<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % x for x in xs), tag)


def overlap(items, ordered):
    """Text1..TextN exactly as Cloze Overlapper generates them.
    Ordered: settings 1,1,0 (one preceding item as context, rest '...').
    Unordered: settings all,1,all (every other item shown)."""
    out = []
    for k in range(len(items)):
        if ordered:
            snip = ["..."] * len(items)
            if k:
                snip[k - 1] = items[k - 1]
        else:
            snip = list(items)
        snip[k] = "{{c%d::%s}}" % (k + 1, items[k])
        out.append(snip)
    return out


def build(spec):
    deck0, tags0, src = spec.get("deck") or "Default", spec.get("tags") or [], esc(spec.get("source"))
    rows, errs, warns, seen, backs = [], [], [], {}, {}
    notes, cards = {BASIC: 0, OVERLAP: 0}, {BASIC: 0, OVERLAP: 0}
    for i, c in enumerate(spec.get("cards", []), 1):
        tags = []
        for t in list(tags0) + list(c.get("tags") or []):
            t = re.sub(r"\s+", "_", str(t).strip())
            if t and t not in tags:
                tags.append(t)
        if c.get("type") == "qa":
            f, b = rich(c.get("front")), rich(c.get("back"))
            if not f or not b:
                errs.append("card %d: front and back required" % i); continue
            key = re.sub(r"\W+", " ", b.lower()).strip()
            if key in backs:
                warns.append("cards %d and %d share an answer: reverse cards ambiguous" % (backs[key], i))
            backs.setdefault(key, i)
            nt, n, fields = BASIC, 2, [f, b, rich(c.get("why"))]
        elif c.get("type") == "list":
            raw = [str(x) for x in c.get("items", []) if str(x).strip()]
            bad = [x for x in raw if "::" in x or "{{" in x or "}}" in x]
            if bad or not 2 <= len(raw) <= OLC_MAX:
                errs.append("card %d: need 2-%d items without '::', '{{', '}}'" % (i, OLC_MAX)); continue
            if len(raw) > 8:
                warns.append("card %d: %d items; split by principle?" % (i, len(raw)))
            if not c.get("title"):
                warns.append("card %d: list has no title" % i)
            items, ordered = [esc(x) for x in raw], c.get("ordered", True)
            full = c.get("full")
            full = (ordered and len(items) <= FULL_MAX) if full is None else bool(full)
            tag = "ol" if ordered else "ul"
            texts = [ul(tag, s) for s in overlap(items, ordered)]
            setting = ("1,1,0" if ordered else "all,1,all") + " | n,n,n," + ("n" if full else "y")
            fields = ([ul(tag, items), esc(c.get("title")), rich(c.get("why")), src, setting]
                      + texts + [""] * (OLC_MAX - len(texts))
                      + [ul(tag, ["{{c%d::%s}}" % (OLC_MAX + 1, x) for x in items]) if full else ""])
            nt, n = OVERLAP, len(texts) + (1 if full else 0)
        else:
            errs.append("card %d: unknown type %r" % (i, c.get("type"))); continue
        if (nt, fields[0]) in seen:
            errs.append("cards %d and %d: same first field (duplicate)" % (seen[(nt, fields[0])], i)); continue
        seen[(nt, fields[0])] = i
        notes[nt] += 1; cards[nt] += n
        rows.append([nt, c.get("deck") or deck0, " ".join(tags)] + fields + [""] * (N_FIELDS - len(fields)))
    cols = ["Note type", "Deck", "Tags"] + ["F%d" % k for k in range(1, N_FIELDS + 1)]
    head = ["#separator:tab", "#html:true", "#notetype column:1", "#deck column:2",
            "#tags column:3", "#columns:" + "\t".join(cols)]
    return "\n".join(head + ["\t".join(r) for r in rows]) + "\n", notes, cards, errs, warns


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("spec"); ap.add_argument("-o", "--out", default="anki_import.txt")
    a = ap.parse_args()
    text, notes, cards, errs, warns = build(json.load(open(a.spec, encoding="utf-8")))
    open(a.out, "w", encoding="utf-8", newline="\n").write(text)
    for w in warns: print("WARNING: " + w, file=sys.stderr)
    for e in errs: print("ERROR (skipped): " + e, file=sys.stderr)
    print("%d Basic (and reversed card) notes -> %d cards; %d Cloze (overlapping) notes -> %d cards; wrote %s"
          % (notes[BASIC], cards[BASIC], notes[OVERLAP], cards[OVERLAP], a.out), file=sys.stderr)
    sys.exit(1 if errs else 0)
```