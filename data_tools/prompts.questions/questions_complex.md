Your task is to act as a user who is searching for documents in large historical archive. 
Create 5 questions / search queries that the are relevant to the text.

The questions should require complex reasoning or information aggregation 
from multiple texts to asnwer. 
The presented text may contain only part of the information needed to answer the question.

## Follow these rules:
1) COMPLEXITY: Do not ask simple Where, "When", "Who" questions. Prefer "Why", "How", "What were the consequences of...".
2) STANDALONE: The question must make sense on its own without seeing the text. 
3) NO PRONOUNS: Use specific names and entities (instead of "he", "this event", etc.).
4) FACTUAL BASIS: The answer (or part of it) must be found in the text, but the question should require the reader to synthesize information.
5) NO LEAKAGE: Do not include the answer within the question itself.
6) NO META-TALK: Do not mention "the text", "the document" or "according to ...".
7) **LANGUAGE:** Match the language of the provided text. If the text is in Czech, ask in Czech. If in German, ask in German.

## Examples of good questions:
- What were the effects of high fuel prices during WW II for agricalcure?
- What were the relations between Czech and Germans is 1935 in north Bohemia?
- Why did the Germans occupy Czech borders?
- Who were the main supporters of T. G. Masaryk for presidency?

## Output format:
Write only a JSON array of the question strings. The example is:

 `["question 1", "question 2", "question 3", "question 4", "question 5"]`

# This text prefix is only for context, do not ask questions about this text:
{prefix_text}



# This is the text for which you should generate 5 questions / search queries:
{text}
