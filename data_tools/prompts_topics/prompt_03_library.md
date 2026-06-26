# Task definition — Public-library tagging tags

We are creating training data for a general text span tagging system. The system will be used by both researchers and members of the public to mark useful passages in older documents from libraries and archives.

Your task is to generate exactly 3 tag names. The tags should be practical, understandable, and useful for non-expert users. Avoid overly technical, abstract, or academic tag names.

Each tag should describe a recognizable kind of content that a reader might want to find again, compare across documents, or use for research. Examples of possible tag focuses include people mentioned, places described, daily life, institutions, conflicts, work, beliefs, rules, public events, economic conditions, or descriptions of material objects.

For each tag, write a clear self-contained description in plain language. The description should explain what a user should mark with the tag and give enough detail to make the tagging consistent.

Then, find all exact spans in the texts that should be marked with each tag.

Choose spans that are useful to a reader. Avoid tagging very long passages unless the whole passage is needed to preserve the meaning.

# Output format
[
    {
        "id": 1,
        "name": "Name 1",
        "description": "Description of tag 1",
        "tag_spans": [
            {
                "text_id": interger text id,
                "span": "exact copy of the text span"
            },
            {
                "text_id": interger text id,
                "span": "exact copy of the text span"
            }
        ]
    },
    {
        "id": 2,
        "name": "Name 2",
        "description": "Description of tag 2",
        "tag_spans": [
            {
                "text_id": interger text id,
                "span": "exact copy of the text span"
            }
        ]
    }
    ...
]


{% for item in text %}
# Text {{loop.index0}}
{{item}}
{%- endfor %}
