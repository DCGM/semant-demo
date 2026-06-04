# Task context
You are annotating digitized library texts for filtering in a search interface of a public web portal.

# Task - information granularity
- Characterize the level of specificity and detail of the information presented in `Text to be classified`.
- Choose one class from the list below that best describes how specific or general the content is.
- Use the provided `Context` only for better understanding, but assign the class relevant only to `Text to be classified`.
- Focus on the specificity and depth of the information, not on complexity, communicative mode, or documentary role.

# Classes
- `general_overview` — broad, panoramic, introductory, or summary treatment of a topic; presents the landscape without going into specific detail
- `detailed_account` — thorough treatment with moderate specificity; develops a topic with supporting detail, examples, or elaboration
- `highly_specific` — narrowly focused, instance-level, or case-specific content; a particular event, individual case, procedure, measurement, or example
- `definitional` — primarily defines, explains, or introduces a concept, term, category, or entity with little further elaboration
- `enumerative` — mainly lists, catalogs, or enumerates items, cases, names, or examples without sustained analytical or narrative development
- `uncertain` — granularity cannot be determined reliably due to corruption, fragmentation, or insufficient content

# Preference rules
- Prefer `general_overview` when the passage surveys a topic from a high level without committing to specific instances or case-level detail.
- Prefer `detailed_account` over `general_overview` when the passage develops a topic with concrete supporting material.
- Prefer `highly_specific` when the passage is clearly about a single instance, event, case, or measurement rather than a type or class of things.
- Prefer `definitional` when the primary purpose is to explain what something is, regardless of passage length.
- Prefer `enumerative` for catalog-like or list-like passages even if they contain brief elaborations per item.
- Use `uncertain` only for severely degraded or empty passages.

# Output
Write only a JSON with reason for classification and one class label and nothing else.

Output example 1: {"reason": "Clear reasoning for the classification with evidence from the text.", "class": "detailed_account"}
Output example 2: {"reason": "Clear reasoning for the classification with evidence from the text.", "class": "highly_specific"}

# Previous context from the document is:
{prefix_text}

# Text to be classified is:
{text}
