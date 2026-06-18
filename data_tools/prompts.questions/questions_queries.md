Your task is to act as a user who is searching for documents in large historical archive. 
Create 5 search queries that the are relevant to the text.

## Follow these rules:
2) STANDALONE: The queries must make sense on its own without seeing the text. 
3) NO PRONOUNS: Use specific names and entities (instead of "he", "this event", etc.).
4) FACTUAL BASIS: The answer (or part of it) must be found in the text.
5) NO LEAKAGE: Do not include the answer within the query itself.
6) NO META-TALK: Do not mention "the text", "the document" or "according to ...".
7) **LANGUAGE:** Match the language of the provided text. If the text is in Czech, ask in Czech. If in German, ask in German.

## Output format:
Write only a JSON array of the question strings. The example is:

 `["query 1", "query 2", "query 3", "query 4", "query 5"]`

# This text prefix is only for context, do not ask questions about this text:
{prefix_text}



# This is the text for which you should generate 5 questions / search queries:
{text}
