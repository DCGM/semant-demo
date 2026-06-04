# Task context
You are annotating digitized library texts for filtering in a search interface of a public web portal.

# Task - named entity focus
- Characterize the type of named entity that the passage primarily revolves around.
- Choose one primary class that best describes the dominant entity focus of the classified passage.
- Optionally choose a second class only if a second entity focus is clearly and substantially present in the classified passage.
- Use the provided `Context` only for better understanding, but assign classes relevant only to `Text to be classified`.
- Focus on what type of named entity the content is primarily about, not on topic, documentary role, or communicative mode.

# Classes
- `person_centric` — the passage primarily revolves around a specific person or persons: biography, obituary, personal profile, or correspondence about individuals
- `organization_centric` — the passage primarily revolves around a named institution, company, association, government body, religious body, or other organized group
- `place_centric` — the passage primarily revolves around a named location, territory, settlement, geographic feature, or region
- `event_centric` — the passage primarily revolves around a specific datable or named event, incident, battle, ceremony, or occurrence
- `work_centric` — the passage primarily revolves around a named text, artwork, composition, publication, law, or other created or enacted artifact
- `concept_or_topic_centric` — the passage primarily discusses an abstract concept, discipline, doctrine, theory, or general theme without a dominant named entity as its subject
- `mixed` — two or more entity types are clearly co-dominant and neither clearly prevails
- `uncertain` — entity focus cannot be determined reliably from the passage

# Preference rules
- Prefer `person_centric` when a named individual or individuals are the primary subject, even if organizations or places are also mentioned.
- Prefer `event_centric` over `place_centric` when the passage is primarily about what happened at or near a place rather than about the place itself.
- Prefer `organization_centric` over `person_centric` when an institution is the primary actor or subject even if named individuals appear.
- Prefer `concept_or_topic_centric` when no specific named entity is the clear focus, regardless of content complexity.
- Use `mixed` only when two entity types genuinely share the focus equally and neither dominates.
- Use `uncertain` only if the text is too fragmentary or ambiguous for reliable classification.

# Output
Write only a JSON with reason for classification and one or two class labels without any additional text or explanation.

Output example 1: {"reason": "Clear reasoning for the classification with evidence from the text.", "classes": ["person_centric"]}
Output example 2: {"reason": "Clear reasoning for the classification with evidence from the text.", "classes": ["event_centric", "place_centric"]}

# Previous context from the document is:
{prefix_text}

# Text to be classified is:
{text}
