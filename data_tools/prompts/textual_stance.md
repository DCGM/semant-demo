# Task context
You are annotating digitized library texts for filtering in a search interface of a public web portal.

# Task
- Characterize the textual stance of `Text to be classified`.
- Choose only from the possible classes below.
- Choose one primary class that best describes the dominant rhetorical stance of the classified passage.
- If multiple classes apply, prefer the most specific class that describes the dominant stance.
- Optionally choose a second class only if a second stance is clearly and substantially present in the classified passage.
- Use the provided `Context` only for better understanding, but assign classes relevant only to `Text to be classified`.
- Focus on how the passage positions its claims, judgments, or attitude, not on structure, topic, documentary role, or factual truth.

# Possible classes
- `neutral_descriptive` — presents information with little overt judgment, persuasion, or emotional positioning
- `interpretive` — frames, explains, or gives meaning beyond straightforward description
- `evaluative` — explicitly judges quality, value, correctness, importance, or blame
- `persuasive` — seeks to convince the reader of a position, action, or belief
- `normative` — states or implies what ought to be done, believed, or valued
- `committed_assertive` — presents claims with strong certainty, authority, or confidence
- `hedged_or_cautious` — presents claims with uncertainty, limitation, caution, or qualification
- `partisan_or_polemical` — strongly aligned, combative, oppositional, or ideologically charged
- `satirical_or_ironic` — uses irony, mockery, parody, or satirical distancing
- `other_stance` — recognizable stance not covered by the available classes
- `uncertain` — stance cannot be determined reliably from the passage

# Preference rules
- Prefer `neutral_descriptive` when the passage mainly presents information without overt judgment or persuasion.
- Prefer `interpretive` over `neutral_descriptive` when the passage clearly frames or explains the significance of what it describes.
- Prefer `evaluative` when the passage primarily judges merit, value, blame, or quality.
- Prefer `persuasive` when the passage mainly tries to convince the reader, even if it also evaluates.
- Prefer `normative` when the passage primarily states what ought to be done, believed, or valued.
- Prefer `partisan_or_polemical` over `persuasive` when the tone is strongly oppositional, ideological, or combative.
- Prefer `satirical_or_ironic` only when irony or satire is clearly signaled in the passage.
- Prefer `hedged_or_cautious` when claims are explicitly limited by uncertainty markers such as possibility, probability, approximation, or caution.
- Prefer `committed_assertive` when claims are presented with strong certainty or authoritative confidence.
- Use `uncertain` if the passage is too fragmentary, ambiguous, or context-dependent for reliable stance classification.

# Output
Write only a JSON list of one or two class labels without any additional text or explanation.

Output example 1: ["neutral_descriptive"]
Output example 2: ["evaluative", "persuasive"]

# Previous context from the document is:
{prefix_text}

# Text to be classified is:
{text}