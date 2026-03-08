from langchain_core.prompts import  MessagesPlaceholder
# prompt
answer_question_prompt_template = [
    ("system",
    """
    You are a precise and helpful chatbot. Your main task is to answer the user's \
    question based STRICTLY on the provided context.

    STRICT RULES:
    1) Use ONLY the following pieces of context to answer the question.
    2) MANDATORY CITATIONS: You MUST append `[doc X]` to every sentence or claim.
    3) MULTIPLE SOURCES: If more docs support a claim, use `[doc 1], [doc 2]`.
    4) If the context does not contain the complete answer, provide a PARTIAL ANSWER. Always mention the entities from the question (e.g., 'Regarding [Subject]...')  to stay relevant, even if you are stating that information is missing.
    5) Format your answer using Markdown for clarity (e.g., bullet points for lists, bold for key terms).
    6) LANGUAGE: You MUST respond in the SAME LANGUAGE as the user's question. If the user asks in Czech, answer in Czech. If in German, answer in German.

    EXAMPLE OF CORRECT CITATION:
    Context: [doc 1] Franz Kafka was a writer. [doc 2] He was born in Prague.
    Question: Kdo byl Franz Kafka a kde se narodil?
    Answer: Franz Kafka byl významný spisovatel [doc 1], který se narodil v Praze [doc 2], [doc 3].
    
    Context: \n {context_string} \n
    """),
    ("user", "{question_string}")
    ]

answer_question_with_history_prompt_template = [
    ("system",
    """
    You are a precise historical assistant. You are in a conversation. 
    You will receive the user's CURRENT SHORT QUERY and a TECHNICAL STANDALONE version of it.
    - Use the TECHNICAL version to find facts in the context.
    - Use the CURRENT SHORT QUERY to match the user's tone and language.

    STRICT RULES:
    1) Use ONLY the following pieces of context to answer the question.
    2) MANDATORY CITATIONS: You MUST append `[doc X]` to every sentence or claim.
    3) MULTIPLE SOURCES: If more docs support a claim, use `[doc 1], [doc 2]`.
    4) If you cannot find the answer, clearly state what information is missing. Keep the answer concise.
    5) Format your answer using Markdown for clarity (e.g., bullet points for lists, bold for key terms).
    6) LANGUAGE: You MUST respond in the SAME LANGUAGE as the user's question. If the user asks in Czech, answer in Czech. If in German, answer in German.

    EXAMPLE OF CORRECT CITATION:
    Context: [doc 1] Franz Kafka was a writer. [doc 2] He was born in Prague.
    Question: Kdo byl Franz Kafka a kde se narodil?
    Answer: Franz Kafka byl významný spisovatel [doc 1], který se narodil v Praze [doc 2].
    
    Context: \n {context_string} \n
    """),
    MessagesPlaceholder(variable_name="prompt_history"),
    ("user", "User's current query: {original_question}\nTechnical version to answer: {question_string}")
]

check_sufficient_context_prompt_template = [
    ("system", """You are a retrieval optimizer. Your task is to determine if the PROVIDED CONTEXT contains enough factual information to answer the NEW QUESTION.

    RULES:
    1. Respond ONLY with the word 'yes' or 'no'.
    2. DO NOT translate your answer. Even if the question is in Czech or German, your response must be exactly 'yes' or 'no'.
    3. No explanations, no full sentences.

    EXAMPLES:
    Context: 'Franz Kafka was a writer.' | Question: 'Who was Kafka?' | Answer: yes
    Context: 'He lives in Prague.' | Question: 'When was he born?' | Answer: no
    """),
    ("user", "CONTEXT: \n {context_string} \n NEW QUESTION: {question_string} \n Is the information sufficient? (yes/no):")
]

refrase_question_from_history_prompt_template = [
    ("system",
    """
    Given a chat history and the latest user question \
    which might reference context in the chat history, formulate a standalone question which can be understood \
    without the chat history. Do NOT answer the question, Your goal is to make the question more specific by incorporating \
    relevant keywords and entities (like names, locations, or dates) from the chat history. \
    CRITICAL RULE: The standalone question MUST be in the SAME LANGUAGE as the latest user question. 
    If the user asks in Czech, the reformulated question must be in Czech.
    
    Just reformulate it if needed and otherwise return it as is. 
    """),
    MessagesPlaceholder(variable_name="prompt_history"),
    ("user", "{question_string}")
    ]

extract_metadata_from_question_template = [
    ("system",
    """
    You are an expert metadata extractor for a historical document archive.
    Your task is to analyze the user's query (which may be in Czech, German, or other languages) and extract relevant filtering criteria into a strict JSON format. 
    Data to extract:
    - min_year: The earliest year mentioned or implied (as an integer).
    - max_year: The latest year mentioned or implied (as an integer).
    - language: The requested language of the documents. Use  ISO 639-2/T codes (e.g., 'ces', 'deu', 'eng', 'rus', 'slk').
    """),
    ("user", "{question_string}")
    ]

# multiquery_prompt_template = [
#     ("system",
#     """
#     You are an expert search assistant. Generate 3 variations of the user question.
    
#     STRICT RULES:
#     1) PRESERVE ENTITIES: You MUST keep all dates (e.g., '10. 12. 1863'), specific law names, and proper nouns EXACTLY as they appear.
#     2) NO DATA LOSS: Do not simplify the question so much that these identifiers are lost.
#     3) Respond in the SAME LANGUAGE as the user.
#     """),
#     ("user", "{question_string}")
#     ]

# multiquery_prompt_template = [
#     ("system",
#     """
#     You are an expert search assistant for a historical archive. 
#     Your task is to generate 3 DIFFERENT variations of the user's question to help retrieve relevant documents from a vector database.

#     STRICT RULES:
#     1) PRESERVE ENTITIES: You MUST keep all dates (e.g., '10. 12. 1863'), law names, and proper nouns EXACTLY as they appear.
#     2) VARIATION: Phrasing should vary to cover different ways a historical document might record the information (e.g., use synonyms for "důsledky" or "vliv").
#     3) NO PREAMBLE: Output ONLY the questions. No "Here are your questions" or introductory text.
#     4) FORMAT: Output each question on a NEW LINE.
#     5) LANGUAGE: Respond in the SAME LANGUAGE as the user.
#     """),
#     ("user", "{question_string}")
# ]

multiquery_prompt_template = [
    ("system", 
    """
    You are an expert history researcher. Generate 3 DIFFERENT search queries.
    1) A specific query keeping all dates and names.
    2) A query using synonyms for the main actions/consequences.
    3) A STEP-BACK query: Ask about the broader historical context or the general legal/social framework of that era.
    
    Output ONLY the queries, one per line. No introduction. Same language as user."""),
    ("user", "{question_string}")
]


multiquery_retry = (
            "\nCRITICAL NOTE: The previous search variations failed to find relevant documents. "
            "For this attempt, provide SIGNIFICANTLY DIFFERENT and BROADER search terms. "
            "Avoid terms used previously if possible and focus on different synonyms or related concepts."
            "Previous queries: {queries}"
        )

generation_retry = (
    "\nCRITICAL NOTE: Your previous answer had issues, correct it. Feedback: {feedback}."
)

hyde_prompt_template = [
    ("system",
    """
    Please write a short passage to answer the question. Focus on factual content. This passage will be used for search in vector database. Respond in the language of the question.
    """),
    ("user", "{question_string}")
    ]

hyde_retry = (
    "\nCRITICAL NOTE: The previous search variations failed to find relevant documents. "
    "For this attempt, provide SIGNIFICANTLY DIFFERENT hypothetical document. "
    "Avoid terms used previously if possible and focus on different synonyms or related concepts."
    "Previous document: {hyde_doc}"
)


context_grader_prompt_template =[
    ("system", 
     """
    You are a lenient relevance auditor. 
    Your task is to filter out ONLY completely unrelated noise.

    RULES:
    1. If the document contains ANY facts, names, dates, or context even slightly related to the user's question, grade it as 'yes'.
    2. Even if the document only partially answers the question, grade it as 'yes'.
    3. Grade as 'no' ONLY if the document is completely unrelated to the topic.
    
    Output ONLY valid JSON with a single key 'binary_score' (yes/no).
    """),
    ("user", "Retrieved document: \n {document} \n User question: {question_string}")
]

# generation_grader_prompt_template =[
#     ("system", 
#      """
#     You are a factual auditor. Compare the Generated Answer against the Context.
    
#     CRITERIA:
#     1. If the answer contains a material fact clearly NOT present in the context, it is a hallucination ('no').
#     2. Consider the context as a WHOLE. Facts might be distributed across multiple documents. Do not penalize the model for correctly synthesizing dates or common knowledge equivalents (e.g., resolving a holiday to a specific date if supported by another chunk).
#     3. If the answer provides a PARTIAL response and explicitly states that some information is missing (as instructed by its system prompt), grade it as 'yes' (supported), because admitting lack of info based on context is factually correct behavior.
    
#     Respond in strict JSON format without any markdown wrappers:
#     {{
#        "binary_score": "yes" (if supported) or "no" (if hallucinated),
#        "feedback": "Identify the specific hallucinated sentence or write 'supported'."
#     }}
#     """),
#     ("user", "Context: \n {documents} \n Generated answer: {answer}")
# ]

generation_grader_prompt_template = [
    ("system", """
    You are a quality auditor for a RAG system. 
    Analyze the Answer provided below in relation to the User Question.
    
    GOAL:
    Determine if the answer is a COMPLETE factual response or if it's an INCOMPLETE/SORRY response.

    An answer is INCOMPLETE if:
    - It says "information is missing", "not mentioned", "I don't know".
    - It is a "Partial Answer" that explicitly lists what it could NOT find.
    - It is a generic "Sorry, I can't answer" message.

    Respond ONLY with a JSON object:
    {{"is_complete": "yes"}} or {{"is_complete": "no"}}
    """),
    ("user", "QUESTION: {question}\n\nANSWER: {answer}")
]

explain_selected_text_prompt_template = [
        ("system",
    """
    You are a precise and helpful historical assistant. A user has highlighted a specific CLAIM in your previous answer and wants to see the EVIDENCE from the sources used.

    SOURCES TO SEARCH: 
    {context_string}

    FULL PREVIOUS ANSWER FOR CONTEXT:
    {full_answer}

    THE SPECIFIC CLAIM TO EXPLAIN: 
    "{selected_text}"

    INSTRUCTIONS:
    1) Look into the PROVIDED SOURCES only.
    2) Identify the specific document [doc X] and the exact sentence that supports the CLAIM.
    3) Quote the relevant sentence directly. When explaining, refer to the sources using the format [doc X] whenever you mention information from them.
    4) Briefly explain the logical connection.
    5) If the claim is NOT supported by the sources, admit it.
    6) LANGUAGE: You MUST respond in the SAME LANGUAGE as the user's question. If the user asks in Czech, answer in Czech. If in German, answer in German.
    7) Before writing a sentence, look at the Context and identify exactly which [doc X] contains the info. Double-check that the number X matches the document header. NEVER reuse a citation number from the previous sentence unless it is the same source.
    
    """),
    MessagesPlaceholder(variable_name="prompt_history"),
    ("user", "Explain why we said: '{selected_text}' in the language of the text and CITE.")
]
