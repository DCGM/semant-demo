# Task definition — Discourse, stance, and rhetorical function tags

We are creating training data for a general text span tagging system. The system will be used to annotate older documents for later linguistic, qualitative, and quantitative analysis.

Your task is to generate exactly 3 tag names. Each tag should focus on how language functions in the text. The tags should capture discourse-level or rhetorical aspects such as explanation, justification, contrast, emphasis, uncertainty, obligation, evaluation, attribution, persuasion, narrative sequencing, or the writer’s stance toward people, events, claims, or conditions.

For each tag, write a self-contained description that defines the discourse or rhetorical function. The description should explain:

* what communicative function the tag captures,
* which linguistic cues may indicate the function,
* when a span should be included,
* when a span should not be included,
* how much surrounding text should be selected.

Then, identify all exact spans in the presented texts that should be marked with each tag.

Marked spans should preserve the rhetorical or discourse function. Do not tag isolated words when the function depends on a larger phrase, clause, or sentence. Do not paraphrase or normalize historical spelling.

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
