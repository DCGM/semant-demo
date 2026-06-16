# Task
- The text is from a scanned older document processed by OCR which transcribes the text but does not uderstand structure of the document.
- The text could be composed of more logical parts (e.g. articles, reports, records, entries, ...).
- Identify the logical parts and write them separately inluding the reason for separating them and a short descriptive title. 
- Split only standalone logical parts. Do not split the text when a topic changes, but it is still part of the same article or a chapter.
- The text must not be split, when it depends on the prevous part, it continues.
- Split the parts only when they are independent and coulbe presented to a reader separately.
- Keep the original textlines.

# Output format 
JSON list of objects with attributes:  `text`, `split_reason.cs`, `title.cs`
- `text` - The full text of the logical part as originally written including the original textlines. Do not add any additional text.
- `split_reason.cs` - In Czech, why was this part separated from the previous one. Should be empty for the first logical part.
- `title.cs` - In Czech, short title which summarizes this part.

# Output example
[
    {
        "text": "Text první části",
        "split_reason.cs": "",
        "title.cs": "Titulek první části"
    },
    {
        "text": "Text druhé části části",
        "split_reason.cs": "Tato část je o tématech druhé části",
        "title.cs": "Titulek druhé části"
    }
]

# The text
{prefix_text}
{text}
{suffix_text}
