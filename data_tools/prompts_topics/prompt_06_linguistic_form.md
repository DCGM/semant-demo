# Task definition — Linguistic form and expression tags

We are creating training data for a general-purpose text span tagging system. The system will be used to mark older documents for qualitative and quantitative text analysis, including analysis of language use, style, and expression.

Your task is to generate exactly 3 tag names. Each tag should focus on a linguistic aspect of the texts rather than only on their subject matter. Tags may describe recurring forms of expression, wording patterns, grammatical constructions, rhetorical phrasing, evaluative language, modality, reported speech, temporal expressions, comparisons, or other language features that can be identified from the wording itself.

For each tag, provide a self-contained description explaining:

* the linguistic feature represented by the tag,
* how the feature can be recognized in text,
* what kinds of spans should be marked,
* what similar but non-qualifying spans should be excluded.

Then, localize all exact spans in the presented texts that should be marked with each tag.

Choose spans that clearly demonstrate the linguistic feature. Prefer the shortest span that fully contains the relevant wording, but include enough context to make the feature understandable.

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
