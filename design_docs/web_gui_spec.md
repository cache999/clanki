## overview
clanki is a web app for my previously manual workflow, transcribing content (e.g. lecture handouts, slides, websites).

Overall, I want to be able to open and read slides or lecture handouts in the app (this should be a large part of the display, as I will be learning/reading the material in this UI). I want to then be able to easily convert what I specify into anki cards:
- I want to be able to highlight portions of text in the document, then run the LLM to generate cards from that portion. I should be able to condition the llm (e.g. if I only want the MoA from a highlighted section containing a drug's moa, use, application - I can type in 'MoA' and the LLM will only generate the relevant card). Unconditioned card generation should follow UKMLA relevance (see claude_skill).
- Also option to generate from all text in the document

- If possible, I'd like to be able to screenshot slide material, OCR into text, then do the same generation.

There should be some sort of display (maybe some sort of sidebar) of the auto-generated anki cards, options to edit/delete/add them, export to a text file for import into Anki etc. Possibly a small 'ongoing jobs' indicator for sections being processed by the LLM

Content is currently medical in nature, but flexibility for the future is desired (this would probably be some sort of configurable to switch prompts - fine with having to hard code-in different prompts in this repo). You can use the skill md (an earlier, non web-app version) as a reference for the learning style I want for medical content.

Check the selected notes; both the cards format and the notes format import into anki. The notes format with the cloze overlap card type is untested, so it would be useful to first test 1) a dummy list in the notes format; 2) a dummy list in the given cards format; 3) a dummy list in a format of your own design.

[note for llms] are notes for this spec, written into the cards (should be adapted into your prompt design.)

LLM integration: is API access to my claude subscription possible? What Anthropic models are available through API?

## ui
- functionality, speed of use, and informativeness are first priority; you can apply graphic design principles but only if the former are satisfied
- keyboard shortcuts for most functionality