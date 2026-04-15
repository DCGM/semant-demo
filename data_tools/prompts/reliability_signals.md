# Task context
You are annotating digitized library texts for filtering in a search interface of a public web portal.

# Task
- Characterize the reliability signals of `Text to be classified`.
- Choose only from the possible classes below.
- Choose one primary class that best describes the dominant evidential or reliability-related signal present in the classified passage.
- If multiple classes apply, prefer the most specific class that describes the dominant signal.
- Optionally choose a second class only if a second signal is clearly and substantially present in the classified passage.
- Use the provided `Context` only for better understanding, but assign classes relevant only to `Text to be classified`.
- Focus on signals visible in the passage, such as evidence, sourcing, certainty, documentation, speculation, or advocacy.
- Do not judge whether the passage is actually true or false. Classify only the reliability-related signals expressed in the passage itself.

# Possible classes
- `evidence_based` — supports claims with cited facts, sources, records, observations, data, or explicit evidence
- `source_attributed` — attributes information to identifiable sources, witnesses, authorities, or documents
- `first_hand_account` — presents information as directly observed or personally experienced
- `procedurally_documented` — presents information in formal, documentary, certified, administrative, legal, or record-based form
- `analytical_inference` — derives claims through reasoning, interpretation, or inference rather than direct evidence alone
- `speculative_or_uncertain` — marks claims as tentative, uncertain, approximate, or conjectural
- `asserted_without_support` — makes claims with little or no visible evidential support in the passage
- `promotional_or_advocacy` — advances a cause, institution, product, or agenda in a way that may reduce neutrality
- `partisan_or_propagandistic` — strongly ideological, one-sided, or propagandistic in a way that may reduce evidential balance
- `fictional_or_imaginative_frame` — presents content within a literary, fictional, poetic, or imaginative frame rather than as documentary factual assertion
- `uncertain` — reliability-related signals cannot be determined reliably from the passage

# Preference rules
- Prefer `evidence_based` when the passage explicitly supports claims with evidence, records, data, citations, or observed facts.
- Prefer `source_attributed` when the passage mainly reports information by naming or clearly indicating a source, witness, authority, or document.
- Prefer `first_hand_account` when the speaker or narrator presents the content as directly experienced or observed.
- Prefer `procedurally_documented` when reliability is signaled mainly by formal documentary, legal, administrative, or certified presentation.
- Prefer `analytical_inference` when the passage mainly reasons from evidence rather than simply presenting it.
- Prefer `speculative_or_uncertain` when the passage openly signals uncertainty, approximation, or conjecture.
- Prefer `asserted_without_support` when claims are presented without visible evidence, attribution, or documentation in the passage.
- Prefer `promotional_or_advocacy` when the passage is mainly advancing a cause, institution, or product.
- Prefer `partisan_or_propagandistic` over `promotional_or_advocacy` when the passage is strongly ideological or politically one-sided.
- Prefer `fictional_or_imaginative_frame` when the passage is clearly literary or imaginative rather than documentary or factual in frame.
- Use `uncertain` if the passage is too fragmentary, ambiguous, or context-dependent for reliable classification.

# Output
Write only a JSON list of one or two class labels without any additional text or explanation.

Output example 1: ["procedurally_documented"]
Output example 2: ["source_attributed", "speculative_or_uncertain"]

# Previous context from the document is:
{{prefix_text}}

# Text to be classified is:
{{text}}