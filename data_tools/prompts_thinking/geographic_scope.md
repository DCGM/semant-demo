# Task context
You are annotating digitized library texts for filtering in a search interface of a public web portal.

# Task - geographic scope
- Characterize the geographic scope of the content of `Text to be classified`.
- Choose one class from the list below that best describes the spatial extent of the topic or subject matter of the passage.
- Use the provided `Context` only for better understanding, but assign the class relevant only to `Text to be classified`.
- Focus on the geographic scope of the content, not on where the document was produced, published, or held.

# Classes
- `hyper_local` — content is about a specific address, building, street, field, estate, or other micro-locality
- `local_or_municipal` — content concerns a specific town, city, village, district, or municipal area
- `regional` — content concerns a historical region, province, county, diocese, or multi-municipal territory below national level
- `national` — content concerns a single nation, kingdom, state, or country as a whole
- `multi_national_or_continental` — content concerns multiple countries, an empire, a continent, or a supra-national region
- `global_or_universal` — content applies to the whole world, humanity in general, or has no meaningful geographic restriction
- `non_geographic` — the content has no meaningful geographic anchoring: abstract concepts, biography without place focus, purely temporal or thematic content
- `uncertain` — geographic scope cannot be determined reliably from the passage

# Preference rules
- Prefer the most specific applicable class: if a passage is about a specific town, use `local_or_municipal` rather than `regional`.
- Prefer `non_geographic` when the content is conceptual, literary, theological, or otherwise spatially unanchored rather than being about a place or geographically bounded set of events.
- Prefer `regional` for content about historical territories, provinces, dioceses, or regions that may not correspond to current national boundaries.
- Prefer `national` when a country or state as a whole is the primary frame of reference, even if localities are mentioned.
- Use `uncertain` only when the passage is too degraded, short, or ambiguous to determine geographic scope.

# Output
Write only a JSON with reason for classification and one class label and nothing else.

Output example 1: {"reason": "Clear reasoning for the classification with evidence from the text.", "class": "local_or_municipal"}
Output example 2: {"reason": "Clear reasoning for the classification with evidence from the text.", "class": "non_geographic"}

# Previous context from the document is:
{prefix_text}

# Text to be classified is:
{text}
