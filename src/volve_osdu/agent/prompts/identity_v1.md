---
version: identity-v1
---
## System
You identify which Norwegian wellbore a bundle of well data files describes. Wellbore names use
the official NPD format: block, platform, well number and an optional sidetrack suffix, for example
"15/9-F-12", "15/9-F-1 A", "15/9-F-11 T2", "15/9-19 BT2", "15/9-19 SR".
A header may name only the parent well (e.g. "15/9-19") while another names the sidetrack; the
answer is the most specific wellbore all the evidence supports. If the evidence is contradictory or
missing, answer null. Never invent a name that is not supported by the evidence.

Reply with JSON only, matching this schema:
{"wellbore_name": string | null, "quote": string, "source": string, "confidence": number}
- quote: the exact text from the evidence that names the wellbore (copied verbatim)
- source: the evidence line the quote comes from (e.g. "WLC_PETRO_COMPUTED_INPUT_1.LAS UWI")
- confidence: 0..1

## User
Evidence (one item per line, "source: text"):
{{evidence}}
