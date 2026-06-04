# Task context
You are annotating digitized library texts for filtering in a search interface of a public web portal.

# Task - quantitative content density
- Assess the density of numerical, statistical, or quantitative content in `Text to be classified`.
- Choose one class from the list below.
- Use the provided `Context` only for better understanding, but assign the class relevant only to `Text to be classified`.
- Focus on whether numbers, measurements, statistics, or quantified data are substantively present, not merely incidental.

# Classes
- `no_quantitative` — the passage contains no numbers or figures of substantive informational value; any numbers present are purely incidental (e.g., page numbers, section numbers)
- `incidental_numbers` — a small number of dates, ages, ordinal references, or counts appear but do not constitute systematic quantitative content
- `moderate_quantitative` — meaningful quantities are present (measurements, prices, population figures, financial amounts, scientific values, etc.) but do not dominate the passage
- `data_rich` — the passage is primarily quantitative in nature: tables, statistical series, systematic numerical data, financial accounts, or scientific measurements are central to its content
- `uncertain` — quantitative content cannot be reliably assessed due to corruption, fragmentation, or ambiguity

# Important rules
- Do not count years or dates used purely as historical anchors as substantial quantitative content; classify as `incidental_numbers`.
- Treat passages dominated by financial tables, statistical tables, or systematic scientific measurements as `data_rich`.
- Use `uncertain` only for severely degraded passages where the presence or absence of quantitative content cannot be determined.

# Output
Write only a JSON with reason for classification and one class label and nothing else.

Output example 1: {"reason": "Clear reasoning for the classification with evidence from the text.", "class": "incidental_numbers"}
Output example 2: {"reason": "Clear reasoning for the classification with evidence from the text.", "class": "data_rich"}

# Previous context from the document is:
{prefix_text}

# Text to be classified is:
{text}
