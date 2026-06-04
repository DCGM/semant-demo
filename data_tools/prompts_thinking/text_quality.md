# Task context
You are annotating digitized library texts for filtering in a search interface of a public web portal.

# Task - text quality
- Assess the text quality and usability of `Text to be classified`.
- Choose one class from the list below that best describes the overall quality and readability of the passage as a text unit.
- Use the provided `Context` only for better understanding, but assign the class relevant only to `Text to be classified`.
- Quality is assessed based on OCR accuracy, structural integrity, and coherence — not on content value or importance.

# Classes
- `clean` — text is well-formed, fluent, and consistently readable with minimal or no OCR errors; meaning is fully preserved
- `minor_errors` — text has occasional OCR artifacts, spelling errors, or garbled characters, but the main meaning and structure are clearly preserved
- `noisy` — text has frequent OCR errors, missing words, or corrupted passages, but the general content is still largely recoverable
- `heavily_degraded` — text has severe corruption, systematic OCR failure, or major gaps; some information may be recoverable but reliability is low
- `unreadable` — text is so corrupted, fragmented, or structurally broken that reliable content extraction is not possible

# Important rules
- Assess the passage as it appears, not what it may have been before digitization.
- Do not confuse archaic language, historical spelling, or domain-specific terminology with OCR errors.
- Do not base the label on content difficulty; use `complexity` for reading difficulty assessment.
- Use `unreadable` only when no coherent meaning can be reliably extracted.

# Output
Write only a JSON with reason for classification and one class label and nothing else.

Output example 1: {"reason": "Clear reasoning for the classification with evidence from the text.", "class": "clean"}
Output example 2: {"reason": "Clear reasoning for the classification with evidence from the text.", "class": "noisy"}

# Previous context from the document is:
{prefix_text}

# Text to be classified is:
{text}
