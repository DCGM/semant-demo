# Task context
You are annotating digitized library texts for filtering in a search interface of a public web portal.

# Task
- Characterize the register/style of `Text to be classified`.
- Choose only from the classes below.
- Choose one primary class that best describes the dominant register/style of the classified passage.
- Optionally choose a second class only if a second register/style is clearly and substantially present in the classified passage.
- Use the provided `Context` only for better understanding, but assign classes relevant only to `Text to be classified`.
- Focus on how the passage is written linguistically and stylistically, not on layout, topic, communicative mode, or documentary role.

# Classes
- `formal` / `formal` — elevated, conventionally polished, institutionally appropriate language
- `neutral` / `neutrální` — relatively unmarked standard prose without strong stylistic coloration
- `informal` / `neformální` — conversational, familiar, colloquial, or socially relaxed language
- `bureaucratic` / `administrativní` — formulaic, procedural, impersonal, office-like, or administrative style
- `scholarly` / `akademický`  — concept-dense, precise, analytic, citation-oriented, or research-like style
- `journalistic` / `publicistick7` — news-like, report-oriented, concise, public-information style
- `didactic` / `výukový` — explanatory, teaching-oriented, learner-guiding style
- `devotional` / `duchovní` — prayerful, reverential, liturgical, or spiritually oriented style
- `literary` / `umělecký` — aesthetically marked, figurative, rhythmically or rhetorically shaped language
- `promotional` / `propagační` — persuasive, attention-seeking, selling, or publicity-oriented style
- `formulaic` / `šablonovitý` — heavily patterned, repetitive, conventionalized wording
- `other_style` — recognizable register/style not covered by the available classes
- `uncertain` — register/style cannot be determined reliably from the passage

# Preference rules
- Prefer `bureaucratic` over `formal` when the passage uses procedural, administrative, record-like, or office-style wording.
- Prefer `formulaic` when repeated conventional wording or fixed phrasing is a dominant stylistic feature.
- Prefer `scholarly` over `formal` when the passage is analytically dense, concept-driven, or research-like in style.
- Prefer `journalistic` over `neutral` when the passage clearly uses news-reporting or periodical-information style.
- Prefer `didactic` over `expository-looking` prose when the passage is clearly written to teach, guide, or instruct learners.
- Prefer `devotional` when the passage is strongly prayerful, reverential, or liturgical in tone.
- Prefer `literary` when aesthetic shaping, figurative language, rhythm, or rhetorical stylization is a dominant feature.
- Prefer `promotional` when the passage is mainly written to attract, persuade, advertise, or publicize.
- Prefer `neutral` when no stronger stylistic marking is clearly dominant.
- Use `other_style` only if the passage has a clear register/style not covered by the listed classes.
- Use `uncertain` only if the text is too fragmentary, ambiguous, or corrupted for reliable classification.

# Output
Write only a JSON with reason for classification and one or two class labels without any additional text or explanation.

- Output example 1: {"reason": "Clear reasoning for the classification with evidence from the text.", "classes": ["neutral"]}
- Output example 2: {"reason": "Clear reasoning for the classification with evidence from the text.", "classes": ["bureaucratic", "formulaic"]}

# Previous context from the document is:
{prefix_text}

# Text to be classified is:
{text}
