# Task context
You are annotating digitized library texts for filtering in a search interface of a public web portal.

# Task - temporal reference frame
- Characterize the temporal reference frame of the content of `Text to be classified`.
- Choose one primary class that best describes what time period or temporal orientation the passage refers to.
- Optionally choose a second class only if a second temporal frame is clearly and substantially present in the classified passage.
- Use the provided `Context` only for better understanding, but assign classes relevant only to `Text to be classified`.
- Focus on the time period the content describes or refers to, not on when the document was written or published.

# Classes
- `contemporary_to_authorship` — the passage describes events, conditions, or situations that were current or recent at the time of writing
- `historical_past` — the passage describes a period clearly prior to the time of writing, treating it as documented past history
- `remote_or_mythological_past` — the passage concerns legendary, biblical, ancient classical, pre-historical, or mythological time
- `future_or_projective` — the passage primarily concerns predictions, plans, forecasts, proposals, or anticipated future states
- `timeless_or_general` — the passage expresses principles, laws, definitions, or universal claims not anchored to a specific time period
- `mixed_temporal` — two or more temporal frames are substantially co-present in the passage
- `uncertain` — temporal reference frame cannot be determined reliably from the passage

# Preference rules
- Prefer `historical_past` over `remote_or_mythological_past` when the events described are within documented history even if distant.
- Prefer `remote_or_mythological_past` when the passage refers to legendary, biblical, ancient classical, or pre-documentary time.
- Prefer `contemporary_to_authorship` when the passage discusses events or conditions as current at the time of writing, even if those events are now historically distant.
- Prefer `timeless_or_general` for passages that express universal laws, scientific principles, religious doctrines, or evergreen factual claims with no meaningful temporal anchoring.
- Prefer `mixed_temporal` only when two frames are genuinely co-dominant, not when one is clearly dominant with minor secondary references.
- Use `uncertain` only if the text is too fragmentary, ambiguous, or corrupted for reliable classification.

# Output
Write only a JSON with reason for classification and one or two class labels without any additional text or explanation.

Output example 1: {"reason": "Clear reasoning for the classification with evidence from the text.", "classes": ["historical_past"]}
Output example 2: {"reason": "Clear reasoning for the classification with evidence from the text.", "classes": ["contemporary_to_authorship", "historical_past"]}

# Previous context from the document is:
{prefix_text}

# Text to be classified is:
{text}
