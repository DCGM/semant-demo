# Task context
You are annotating digitized library texts for filtering in a search interface of a public web portal.

# Task - narrative perspective
- Characterize the dominant grammatical person and narrative perspective of `Text to be classified`.
- Choose one primary class that best describes the dominant perspective in the classified passage.
- Optionally choose a second class only if a second perspective is clearly and substantially present in the classified passage.
- Use the provided `Context` only for better understanding, but assign classes relevant only to `Text to be classified`.
- Focus on grammatical person and narrator positioning, not on topic, documentary role, or communicative mode.

# Classes
- `first_person_singular` — the dominant voice is I/me; memoir, personal testimony, diary, personal letter, or first-person narrative
- `first_person_plural` — the dominant voice is we/us; collective or institutional voice, manifesto, communal declaration, or editorial "we"
- `second_person` — primarily addressed to you; instructions, direct address, epistolary address, or prescriptive text
- `third_person_personal` — primarily he/she/they, focused on specific named or identifiable persons; biography, chronicle, narrative report
- `third_person_impersonal` — primarily impersonal, passive, or nominalized constructions; no prominent personal agent; reference text, scientific description, or administrative record
- `mixed_or_shifting` — two or more perspectives are substantially present and none clearly dominates
- `uncertain` — perspective cannot be determined reliably from the passage

# Preference rules
- Prefer `first_person_singular` over `first_person_plural` when the I-voice clearly dominates even if we appears occasionally.
- Prefer `third_person_impersonal` over `third_person_personal` for administrative, scientific, and procedural texts where agents are systematically suppressed or nominalized.
- Prefer `mixed_or_shifting` only when two perspectives are genuinely co-present, not when one is clearly dominant with occasional secondary use.
- Use `uncertain` only for severely fragmented or corrupted passages.

# Output
Write only a JSON with reason for classification and one or two class labels without any additional text or explanation.

Output example 1: {"reason": "Clear reasoning for the classification with evidence from the text.", "classes": ["third_person_personal"]}
Output example 2: {"reason": "Clear reasoning for the classification with evidence from the text.", "classes": ["first_person_singular", "second_person"]}

# Previous context from the document is:
{prefix_text}

# Text to be classified is:
{text}
