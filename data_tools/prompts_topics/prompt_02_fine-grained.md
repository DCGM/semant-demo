# Task definition — Fine-grained span annotation tags

We are creating training data for a general-purpose text span tagging system. The system will be used to mark precise spans in older documents for later qualitative and quantitative analysis.

Your task is to generate exactly 3 tag names. Each tag should identify a relatively specific and repeatable category of textual content. Avoid tags that are so broad that most of the text would qualify.

For each tag, provide a self-contained operational description. The description should be detailed enough that another annotator could apply the tag consistently. Include:

* the core definition of the tag,
* inclusion criteria,
* exclusion criteria,
* guidance on how long the marked span should be.

Then, localize all exact spans in the presented texts that should be marked with each tag.

Prefer the shortest span that fully expresses the relevant content. A valid span may be a phrase, clause, sentence, or multi-sentence passage, but it must be copied exactly from the source text.

Do not invent spans, paraphrase spans, or correct spelling in spans.

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
