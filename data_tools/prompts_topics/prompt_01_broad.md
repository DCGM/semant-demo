# Task definition - Broad thematic tags

We are creating training data for a general-purpose text span tagging system. The system will be used by a wide range of users to tag meaningful text spans in older documents, including library materials, historical texts, public records, and other document collections.

Your task is to generate exactly 3 tag names. Each tag should represent a broad recurring theme, topic, or subject area that appears in the presented texts.

For each tag, provide a self-contained description explaining what kinds of text spans should be marked with that tag. The description should be understandable without reading the original texts. It should define the tag broadly enough to apply across multiple paragraphs, but precisely enough to guide consistent span selection.

Then, localize all exact spans in the presented texts that should be marked with each tag.

A tag span should be a meaningful phrase, sentence, or short passage that directly expresses the tag’s theme. Do not tag spans that are only vaguely related.

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
