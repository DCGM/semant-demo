# Task context
You are annotating digitized library texts for filtering in a search interface of a public web portal.

# Task
- Characterize structural form of the text
- Choose only from the "possible classes"
- Choose one dominant structural class 
- Optionally, choose second relevant class if it is clearly present in the classified passage
- Prefer the more specific class over the more general one.
- Use the provided `Context` for better understanding, but select classes relevant only for `Text to be classified`.

# Possible classes
- `continuous_prose` — running prose organized mainly as sentences and paragraphs
- `verse_lines` — line-based poetic, hymn-like, or psalm-like text
- `list_or_enumeration` — itemized or sequential entries, often one per line
- `tabular` — information arranged in rows/columns or table-like cells
- `form_based_record` — template-like or field-based entry with repeated slots such as name, date, place, amount
- `ledger_or_account_entry` — accounting-style structured entries, balances, debits, credits, itemized transactions
- `header_or_title_block` — headline, title, section heading, dateline, rubric, caption
- `dialogue_turns` — alternating speakers or conversational turns, including dramatic dialogue and interview-style exchange
- `navigation_or_reference_apparatus` — text whose main purpose is to organize, locate, cross-reference, or identify content, such as tables of contents, indexes, bibliographies, glossaries, or catalog-style reference material
- `quoted_block` — visually or editorially marked sustained quotation or excerpt
- `entry_like_units` — sequence of short self-contained entries, notices, or records, typically one item per line or paragraph such as dictionary or chronicle records, short news, ...
- `other_structure` — recognizable structure not covered by other available classes
- `garbage` — OCR-corrupted, fragmentary, or structurally unreadable text where no reliable class can be assigned

# Preference rules
- Prefer `ledger_or_account_entry` over `tabular` for accounting or transaction material.
- Prefer `form_based_record` over `list_or_enumeration` when repeated fields or slots are present.
- Prefer `navigation_or_reference_apparatus` over `list_or_enumeration` when the main purpose is lookup, navigation, or reference.
- Prefer `continuous_prose` over `quoted_block` unless the passage is clearly presented as a sustained quotation.

# Output
Write only a JSON list of one or two classes without any additional text or explanation.

Output example 1: ["continuous_prose"]
Output example 2: ["header_or_title_block", "continuous_prose"]

# Preceding context from the document is:
{prefix_text}

# Text to be classified is:
{text}
