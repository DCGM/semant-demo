# Task specification - generate queries and query-based titles
We need to create examples of possible user queries for a information retrieval (or RAG) system which is used to retrieve information from historical documents stored in a library or an archive. The system may be used by researchers, historians, students, or anyone interested in exploring historical texts. The system also provided the users with short generated titles relevant to their search queries.

Your task is to read the provided text, write several possible user search queries, and provide an informative query-based title for each. Write the queries and titles only in Czech language.

# Queries
Provide diverse queries of three types:
1. `factual_search_query` - Factual search-like queries: Classic key-word like search queries. Example: narozeniny Jana Amose Komenského, bitva u Hradce Králové 1866, válečné zločiny, ...
2. `factual_question_query` - Factual queries formed as a question: Example: Kdy se narodil Jan Amos Komenský?, Kdo vyhrál bitvu u Hradce Králové 1866?, Jaké jsou hlavní válečné zločiny spáchané během druhé světové války?, ...
3. `exploratory_research_query` - Exploratory or research-oriented queries: These queries are broader and may require the system to gather and synthesize information from multiple documents. Example: Jaké byly hlavní změny ve vzdělávání v 17. století? Jaké byly vztahy čechů a němců v českém pohraničí v 19. století? Jak dopadala první světová válka na každodenní život obyčejných lidí?, ...

Ensure the queries cover a range of topics mentioned in the text and reflect different ways users might seek information.
Ensure the queries are relevant to the content of the document provided.

Create 3 distinct queries of each type (factual_search_query, factual_question_query, exploratory_research_query)

# Titles
The titles must summarize information from the text which is relevant to the query. User will decide based on the title if the text is relevant for him or not.
- The titles must be short (at most 8 words)
- The title should be specific for the query and focus only on information relevant to the query.
- Do not repeat the query or parts of it.
- Use only information from the provided text. Do not include any outside knowledge.
- Be faithful, concise, and human-readable.
- Stay factual and concise.
- Keep the titles informative. The goal is not to attract the reader in any undue way. The goal is only to provide relevant short summary.
- Do not invent or exaggerate information.  
- Use neutral, factual, and fluent language.  

# Output
JSON list of objects where each key is a unique query with a title. Objects have these keys:
- `query_type` - string with options factual_search_query, factual_question_query, exploratory_research_query
- `query` - query string
- `title` - title string

# This text precedes the the section of interest. Use this for context. The title does not need to represent this text.
{prefix_text}

# Text for which the titles should be generated. Make sure you represent the content of this text well.
{text}






