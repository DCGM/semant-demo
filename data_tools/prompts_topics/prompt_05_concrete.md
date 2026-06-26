# Task definition — Concrete information tags

We are creating training data for a general-purpose text span tagging system. The system will be used to prepare older documents for qualitative and quantitative text analysis, and also by public users marking documents from libraries and archives.

Your task is to generate exactly 3 tag names. Each tag should focus on a concrete type of information found in the texts, such as persons, places, institutions, events, dates, objects, actions, claims, causes, consequences, or descriptions of conditions.

For each tag, write a self-contained description that clearly defines the information type. The description should specify:

* what textual evidence qualifies for the tag,
* what kinds of spans should be selected,
* what similar but non-qualifying spans should be excluded.

Then, identify every exact text span that should be marked with each tag.

Prefer spans that are specific and informative. Avoid overly broad passages when a shorter phrase or sentence captures the relevant information.

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
