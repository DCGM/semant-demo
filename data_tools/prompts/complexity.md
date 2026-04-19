# Task context
You are annotating digitized library texts for filtering in a search interface of a public web portal.

# Task - reading complexity
- Characterize the reading complexity of `Text to be classified`.
- Choose one class from the possible classes below that best describes how difficult the passage is for a competent present-day reader to understand.
- Use the provided `Context` only for better understanding, but assign the class relevant only to `Text to be classified`.
- Judge complexity based on the passage itself, not on assumed prestige, genre, or topic alone.

# Possible classes
- `very_easy` — very simple vocabulary and syntax, explicit meaning, minimal background knowledge required
- `easy` — generally accessible language and structure, low conceptual density, and limited specialized terminology
- `moderate` — standard educated-reader difficulty, with some abstraction, nontrivial structure, or moderately specialized vocabulary
- `advanced` — dense syntax, abstract concepts, specialized terminology, or substantial background knowledge required
- `expert` — highly specialized, technically dense, conceptually compressed, or philologically difficult text intended mainly for experts
- `uncertain` — complexity cannot be determined reliably due to corruption, fragmentation, ambiguity, or insufficient text

# Evaluation criteria
Consider all of the following:
- syntactic complexity
- vocabulary difficulty
- conceptual abstraction
- information density
- degree of assumed background knowledge
- amount of domain-specific terminology

# Important rules
- Do not treat OCR corruption or damaged text by itself as high complexity; use `uncertain` if readability is too degraded.
- Do not base the label only on document type.
- Use `expert` only for genuinely specialized, highly technical, or very difficult scholarly, legal, medical, scientific, theological, or philological material.
- Use `very_easy` only for genuinely very simple material such as basic primers, children’s educational text, simple notices, or highly explicit and simple instructional text.

# Output
Write only a JSON string containing one class label and nothing else.

Output example 1: "moderate"
Output example 2: "advanced"

# Previous context from the document is:
{{prefix_text}}

# Text to be classified is:
{{text}}
