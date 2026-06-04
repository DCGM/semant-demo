# Task context
You are annotating digitized library texts for filtering in a search interface of a public web portal.

# Task - chunk self-containedness
- Assess how self-contained `Text to be classified` is as a standalone informational unit.
- Choose one class from the list below.
- Use the provided `Context` only for better understanding, but assess the self-containedness of `Text to be classified` alone — that is, how intelligible and useful the passage would be to a reader encountering it without surrounding context.
- Focus on intelligibility and informational completeness, not on length or stylistic quality.

# Classes
- `fully_self_contained` — the passage conveys coherent, complete information on its own; a reader can understand its meaning and purpose without any surrounding context
- `mostly_self_contained` — the passage is largely intelligible as a standalone unit, but has minor context dependencies (e.g., a reference to a previously named subject, or a follow-up remark that enriches but does not complete the main idea)
- `context_dependent` — the passage substantially depends on surrounding text for its meaning: it continues a thought, relies on an unresolved pronoun or reference, refers to a preceding enumeration, or is incomplete without prior framing
- `frame_only` — the passage consists mainly of structural scaffolding without substantive content: headings, page headers, captions, running titles, section markers, or similar navigational elements
- `fragmentary_or_corrupt` — the passage is too damaged, truncated, or fragmented to be reliably used as an informational unit regardless of context

# Preference rules
- Prefer `mostly_self_contained` over `context_dependent` when the passage conveys its main idea independently even if minor details require context.
- Prefer `frame_only` when the passage contains almost no extractable substantive information beyond structural marking.
- Prefer `fragmentary_or_corrupt` over `context_dependent` when the dependency arises primarily from OCR corruption or physical truncation rather than from the text's own structure.

# Output
Write only a JSON with reason for classification and one class label and nothing else.

Output example 1: {"reason": "Clear reasoning for the classification with evidence from the text.", "class": "fully_self_contained"}
Output example 2: {"reason": "Clear reasoning for the classification with evidence from the text.", "class": "context_dependent"}

# Previous context from the document is:
{prefix_text}

# Text to be classified is:
{text}
