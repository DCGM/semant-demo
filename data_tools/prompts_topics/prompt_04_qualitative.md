# Task definition — Qualitative analysis codes

We are creating training data for a text span tagging system intended to support qualitative and quantitative analysis of older documents. The system should learn to create useful analytical tags, not only surface-level labels.

Your task is to generate exactly 3 tag names. Each tag should function as a qualitative analysis code: it should capture a recurring idea, social relation, argument, value judgment, problem, motivation, practice, or pattern of meaning in the texts.

For each tag, provide a self-contained analytical description. The description should explain:

* the concept represented by the tag,
* why this concept is useful for interpreting the texts,
* what evidence in the text should be tagged,
* the boundary between relevant and irrelevant spans.

Then, localize all exact spans that should be marked with each tag.

Select spans that provide evidence for the analytical concept. These may include descriptive statements, explanations, reported actions, evaluations, or claims. Do not tag isolated words unless the word itself is the meaningful evidence.

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
