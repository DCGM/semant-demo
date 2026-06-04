# Task context
You are annotating digitized library texts for filtering in a search interface of a public web portal.

# Task - intertextual density
- Assess the density of citations, quotations, and explicit references to other texts, authorities, or sources in `Text to be classified`.
- Choose one class from the list below.
- Use the provided `Context` only for better understanding, but assign the class relevant only to `Text to be classified`.
- Focus on explicit references visible in the passage: cited works, quoted passages, named authorities, footnote-like attributions, or bibliographic apparatus.

# Classes
- `no_references` — the passage contains no citations, quotations, explicit source references, or named authorities
- `sparse` — one or a few references, attributions, or quotations appear but are not a dominant feature
- `moderate` — several references are present; they support or illustrate the text but do not dominate it
- `dense` — the passage is heavily citation-driven, quotation-heavy, or structured around explicit references to other texts or authorities
- `uncertain` — cannot be reliably assessed due to corruption, fragmentation, or ambiguity

# Important rules
- Count only explicit, traceable references: named authors, titled works, documentary sources, direct quotations, or parenthetical citations.
- Do not count vague allusions, common-knowledge claims, or unmarked paraphrases as explicit references.
- Passages that are themselves quotations or excerpts should be classified based on references visible within them, not by their status as excerpts.
- Use `uncertain` only for severely degraded passages where the presence or absence of references cannot be determined.

# Output
Write only a JSON with reason for classification and one class label and nothing else.

Output example 1: {"reason": "Clear reasoning for the classification with evidence from the text.", "class": "no_references"}
Output example 2: {"reason": "Clear reasoning for the classification with evidence from the text.", "class": "dense"}

# Previous context from the document is:
{prefix_text}

# Text to be classified is:
{text}
