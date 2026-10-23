# Feedback on Nebius Token Factory and NVIDIA Nemotron

Running notes for the hackathon submission's feedback section. Add to it while building.

## 2026-10-22: first live calls (all five Nemotron models)

- **Strict JSON works everywhere.** `response_format: {"type": "json_schema", "strict": true}` returned valid,
  schema-shaped JSON on Lightning, Nano, Super, Ultra and Super-VL. That let us drop prompt-only JSON and most
  defensive parsing. The docs don't say this is supported for Nemotron models; saying so would save teams a probe.
- **Lightning with thinking on breaks structured output.** With `chat_template_kwargs.enable_thinking: true`,
  Nemotron 3.5 Lightning writes its reasoning ("Here's a thinking process: ...") straight into `content`, with no
  `<think>` tags and no `reasoning_content`, and used the whole `max_tokens` budget. We never enable thinking on
  Lightning. Either separating it like the larger models or documenting the behaviour would help.
- **Super, Ultra and Super-VL separate reasoning cleanly** into `message.reasoning_content`, and strict JSON still
  works with thinking on. Ultra used about 1,000-1,400 thinking tokens on our "fit plans to usage" prompt
  (~4 s, ~$0.005 per call).
- **Speed** on short prompts with thinking off: Lightning ~0.7-0.9 s, Nano ~0.5-0.6 s, Super / Ultra / Super-VL
  ~0.5-0.9 s. Fifteen emails in parallel (8 at a time) took ~2.4 s on Lightning.
- **Lightning over-labels receipts.** Out of the box it called a grocery receipt an app-store receipt. One line in
  the prompt fixed it.
- **Merchant names come back "as written"** ("Chipotle" for a DoorDash order, "Duolingo" for Super Duolingo).
  That's reasonable, but it means app code must map names to its own catalog. We do that in code.
- The `/v1/models` listing matches the public catalog's IDs exactly, which made setup easy.
