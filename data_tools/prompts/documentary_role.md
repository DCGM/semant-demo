# Task context
You are annotating digitized library texts for filtering in a search interface of a public web portal.

# Task
- Characterize the documentary role of `Text to be classified`.
- Choose only from the possible classes below.
- Choose one primary class that best describes the dominant documentary sphere or institutional role of the classified passage.
- If multiple classes apply, prefer the most specific class that describes the dominant role of the passage.
- Optionally choose a second class only if a second documentary role is clearly and substantially present in the classified passage.
- Use the provided `Context` only for better understanding, but assign classes relevant only to `Text to be classified`.
- Focus on what kind of documentary or institutional sphere the passage belongs to, not on layout, communicative mode, or topic.

# Possible classes
- `journalistic` — passage belongs to news, periodical, or press communication
- `scholarly` — passage belongs to research, academic, scientific, or learned discourse
- `literary` — passage belongs to imaginative, poetic, dramatic, or literary-aesthetic writing
- `legal` — passage belongs to legal, judicial, legislative, or notarial discourse
- `administrative` — passage belongs to bureaucratic, governmental, institutional, or record-keeping activity
- `religious` — passage belongs to devotional, liturgical, doctrinal, or ecclesiastical discourse
- `educational` — passage belongs to teaching, school, instructional, or pedagogical material
- `commercial` — passage belongs to trade, business, advertising, accounting, or market-oriented communication
- `personal` — passage belongs to private, family, autobiographical, or personal communication
- `official_public_communication` — passage belongs to public-facing official announcements, proclamations, notices, or civic communication
- `reference` — passage belongs to lookup, cataloging, glossary, bibliographic, indexical, or other reference-oriented material
- `other_role` — recognizable documentary role not covered by the available classes
- `uncertain` — documentary role cannot be determined reliably from the passage

# Preference rules
- Prefer `legal` over `administrative` when the passage is primarily legal, judicial, legislative, contractual, or notarial in nature.
- Prefer `administrative` over `official_public_communication` when the passage is mainly an internal or procedural institutional record rather than a public notice or proclamation.
- Prefer `official_public_communication` when the passage is an official text explicitly intended for public announcement, proclamation, notice, or civic instruction.
- Prefer `journalistic` over `official_public_communication` when the passage belongs to a newspaper, magazine, or periodical press context rather than being issued by an authority itself.
- Prefer `scholarly` over `educational` when the passage primarily contributes to research or learned discussion rather than teaching or school use.
- Prefer `educational` over `scholarly` when the passage is primarily written to teach learners rather than to advance research.
- Prefer `personal` over `literary` for private correspondence, diaries, memoir-like notes, or autobiographical records not mainly intended as literary works.
- Prefer `reference` when the passage mainly serves lookup, indexing, bibliography, glossary, cataloging, or navigation purposes.
- Use `other_role` only if the passage has a clear documentary role not covered by the listed classes.
- Use `uncertain` only if the text is too fragmentary, ambiguous, or corrupted for reliable classification.

# Output
Write only a JSON list of one or two class labels without any additional text or explanation.

Output example 1: ["legal"]
Output example 2: ["administrative", "legal"]

# Previous context from the document is:
{{prefix_text}}

# Text to be classified is:
{{text}}