# Task context
You are annotating digitized library texts for filtering in a search interface of a public web portal.

# Task - subject domain
- Classify the subject domain of `Text to be classified` using the classes below, which are based on the ten main classes of the Dewey Decimal Classification (DDC) system as used by libraries worldwide, extended with additional classes for document types common in library collections.
- Choose one primary class that best describes the dominant subject matter of the classified passage.
- Optionally choose a second class only if a second subject domain is clearly and substantially present in the classified passage.
- If the passage has no identifiable subject domain — for example, if it is purely structural, navigational, formulaic, or too generic — output an empty list for `classes`.
- Use the provided `Context` only for better understanding, but assign classes relevant only to `Text to be classified`.
- Focus on the subject content of the passage, not on its documentary role, communicative mode, register, or stylistic form.

# Classes
The core classes follow the ten DDC main divisions. Additional classes cover document types frequent in library collections that do not map cleanly to a subject domain.

**DDC subject classes:**
- `ddc_000_generalia` (DDC 000) — general encyclopedias, bibliographies, information science, library science, museum science, general knowledge collections
- `ddc_100_philosophy_psychology` (DDC 100) — philosophy, metaphysics, epistemology, logic, ethics, aesthetics, psychology, parapsychology
- `ddc_200_religion` (DDC 200) — religion, theology, scripture, religious practice and ritual, church history, devotional literature, mythology and comparative religion
- `ddc_300_social_sciences` (DDC 300) — sociology, economics, law, political science, public administration, military science, social problems, education, trade and commerce, customs, folklore, statistics
- `ddc_400_language` (DDC 400) — linguistics, phonology, grammar, etymology, language history, lexicography, specific languages and their study
- `ddc_500_natural_sciences` (DDC 500) — mathematics, astronomy, physics, chemistry, earth sciences, paleontology, biology, botany, zoology, natural history
- `ddc_600_applied_sciences` (DDC 600) — medicine and health, engineering and technology, agriculture, home economics, management science, architecture and building construction, chemical technology, manufacturing
- `ddc_700_arts_recreation` (DDC 700) — fine arts, sculpture, drawing, painting, photography, music, performing arts (theatre, film, dance), sports, games, and other recreational activities
- `ddc_800_literature` (DDC 800) — literary works (fiction, poetry, drama, essays, satire) and literary criticism, rhetoric, and history of literature; classified by literary form and language of the work
- `ddc_900_history_geography` (DDC 900) — history, biography, genealogy, geography, travel writing, regional and country description, archaeology

**Extended classes for library document types:**
- `news_and_current_affairs` — newspaper articles, press reports, news commentaries, current-affairs journalism, and periodical coverage of events; use when the passage belongs to the news press and its subject is not better captured by a specific DDC class
- `official_and_legal_documents` — proclamations, decrees, ordinances, court records, contracts, administrative circulars, and other official or legal instruments; use when the passage is primarily a documentary legal or administrative artifact rather than a text about law as a subject
- `personal_and_private_documents` — private correspondence, diaries, memoirs, family records, personal notes; use when the passage is a personal document rather than authored for a public subject audience
- `commercial_and_trade_documents` — invoices, price lists, trade catalogs, advertisements, business correspondence, financial records; use when the passage is a commercial artifact rather than a text about economics or trade as a subject
- `uncertain` — subject domain cannot be determined reliably from the passage

# Preference rules
- Prefer `ddc_300_social_sciences` for texts *about* law, economics, politics, education, commerce, or social conditions as subjects; prefer `official_and_legal_documents` when the passage *is* a legal or administrative instrument.
- Prefer `ddc_900_history_geography` for biographical, genealogical, travel, regional description, and historical narrative texts.
- Prefer `ddc_800_literature` for literary works themselves (novels, poems, plays, essays) as well as literary criticism and history of literature.
- Prefer `ddc_200_religion` for devotional, theological, liturgical, and ecclesiastical texts.
- Prefer `ddc_600_applied_sciences` for medical, engineering, agricultural, and applied technological content.
- Prefer `ddc_500_natural_sciences` for mathematical, scientific, or natural history content without a strong applied focus.
- Prefer `ddc_700_arts_recreation` for texts about specific artworks, musical works, performances, artists, or recreational activities.
- Prefer `news_and_current_affairs` for newspaper or periodical passages whose subject is too general, mixed, or topical to map to a specific DDC class; if the news passage has a clear specific subject (e.g., a science article, a legal report), assign the subject-specific DDC class instead.
- Prefer `ddc_000_generalia` for truly encyclopedic, bibliographic, or information-science texts; do not use it as a fallback for generic passages.
- Output an empty `classes` list when the passage has no assignable subject — e.g., purely structural text, formulaic filler, or navigational apparatus.
- Use `uncertain` only if the text is too fragmentary, ambiguous, or corrupted for reliable classification.

# Output
Write only a JSON with reason for classification and zero, one, or two class labels without any additional text or explanation.

Output example 1: {"reason": "Clear reasoning for the classification with evidence from the text.", "classes": ["ddc_900_history_geography"]}
Output example 2: {"reason": "Clear reasoning for the classification with evidence from the text.", "classes": ["ddc_300_social_sciences", "ddc_900_history_geography"]}
Output example 3 (no subject): {"reason": "The passage is a page header with no subject content.", "classes": []}

# Previous context from the document is:
{prefix_text}

# Text to be classified is:
{text}
