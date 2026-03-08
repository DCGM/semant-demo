from langchain_core.prompts import  MessagesPlaceholder
# prompt
# answer_question_prompt_template = [
#     ("system",
#     """
#     You are a precise and helpful chatbot. Your main task is to answer the user's \
#     question based STRICTLY on the provided context.

#     STRICT RULES:
#     1) Use ONLY the following pieces of context to answer the question.
#     2) MANDATORY CITATIONS: You MUST append `[doc X]` to every sentence or claim.
#     3) MULTIPLE SOURCES: If more docs support a claim, use `[doc 1], [doc 2]`.
#     4) Don't make up any new information. If the context does not contain the complete answer, provide a PARTIAL ANSWER based on what IS in the context, and explicitly state what information is missing.
#     5) Format your answer using Markdown for clarity (e.g., bullet points for lists, bold for key terms).
#     6) LANGUAGE: You MUST respond in the SAME LANGUAGE as the user's question. If the user asks in Czech, answer in Czech. If in German, answer in German.

#     EXAMPLE OF CORRECT CITATION:
#     Context: [doc 1] Franz Kafka was a writer. [doc 2] He was born in Prague.
#     Question: Kdo byl Franz Kafka a kde se narodil?
#     Answer: Franz Kafka byl významný spisovatel [doc 1], který se narodil v Praze [doc 2].
    
#     Context: \n {context_string} \n
#     """),
#     ("user", "{question_string}")
#     ]

answer_question_prompt_template = [
    ("system", """
    Jsi odborný historik. Odpovídej plynule v češtině.
    
    PRAVIDLA:
    1) Odpověď začni PŘÍMO fakty. Nepoužívej úvody jako "Ohledně...", "Na základě..." nebo "V kontextu...".
    2) Piš v odstavcích, buď věcný, ale ne strohý.
    3) Každé tvrzení cituj pomocí [doc X].
    4) Pokud kontext neobsahuje informaci, v odpovědi ji úplně VYNECHEJ. Nepiš o tom, co v textu není. 
       Jen pokud v kontextu není VŮBEC NIC k tématu, napiš jedinou větu: "K tomuto tématu chybí v dostupných pramenech podklady."
     
    Kontext: \n {context_string} \n
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
    4) Don't make up any new information. If you can not provide answer based on the context, answer only \"Sorry, I can´t answer the question.\".
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
#     You are an expert search query assistant for a historical archive. 
#     Your task is to generate 3 to 5 different versions of the user's question to retrieve relevant documents from a vector database. 
#     By providing multiple perspectives on the same question, your goal is to overcome issues with keyword-based or semantic search limitations.
    
#     Follow these rules exactly:
#     1) Generate 3 to 5 variations of the question.
#     2) Keep the original meaning but use different synonyms or phrasing.
#     3) Output each question on a NEW LINE.
#     4) Do NOT include numbers, bullet points, or any introductory text.
#     5) Respond in the SAME LANGUAGE as the user's question.
#     """),
#     ("user", "{question_string}")
#     ]

multiquery_prompt_template = [
    ("system",
    """
    You are an expert search assistant. Generate 3 variations of the user question.
    
    STRICT RULES:
    1) PRESERVE ENTITIES: You MUST keep all dates (e.g., '10. 12. 1863'), specific law names, and proper nouns EXACTLY as they appear.
    2) NO DATA LOSS: Do not simplify the question so much that these identifiers are lost.
    3) Respond in the SAME LANGUAGE as the user.
    """),
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

# context_grader_prompt_template = [
#     ("system", 
#      """
#     You are a grader assessing relevance of a retrieved document to a user question. 
#     If the document contains keywords or semantic meaning related to the user question, grade it as relevant. 
#     Give a binary score 'yes' or 'no' score to indicate whether the document is relevant to the question.
    
#     Output ONLY valid JSON with a single key 'binary_score'.
#     """),
#     ("user", "Retrieved document: \n {document} \n User question: {question_string}")
# ]

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

# generation_grader_prompt_template = [
#     ("system", 
#      """
#     You are a strict quality controller. 
#     Your task is to check if the generated answer is fully supported by the provided context.
    
#     Follow these rules exactly:
#     1. If the answer contains information NOT present in the context, it is a hallucination and 'binary_score' have to be 'no'.
#     2. Respond in JSON format with two keys:
#        - 'binary_score': 'yes' if supported, 'no' if not.
#        - 'feedback': A short explanation of what is wrong or missing. It should be useful for generating improved responses.
#     """),
#     ("user", "Context: \n {documents} \n Generated answer: {answer}")
# ]

# generation_grader_prompt_template = [
#     ("system", 
#      """
#     You are a strict factual auditor. 
#     Compare the Generated Answer against the Context.
    
#     CRITERIA:
#     1. If the answer contains ANY fact not present in the context, it is a hallucination.
#     2. Be very strict about dates and numbers.
    
#     Respond in JSON format:
#     {{
#        "binary_score": "yes" (if fully supported) or "no" (if there is a hallucination),
#        "feedback": "Identify the specific hallucinated sentence."
#     }}
#     """),
#     ("user", "Context: \n {documents} \n Generated answer: {answer}")
# ]

generation_grader_prompt_template =[
    ("system", 
     """
    You are a factual auditor. Compare the Generated Answer against the Context.
    
    CRITERIA:
    1. If the answer contains a material fact clearly NOT present in the context, it is a hallucination ('no').
    2. Consider the context as a WHOLE. Facts might be distributed across multiple documents. Do not penalize the model for correctly synthesizing dates or common knowledge equivalents (e.g., resolving a holiday to a specific date if supported by another chunk).
    3. If the answer provides a PARTIAL response and explicitly states that some information is missing (as instructed by its system prompt), grade it as 'yes' (supported), because admitting lack of info based on context is factually correct behavior.
    
    Respond in strict JSON format without any markdown wrappers:
    {{
       "binary_score": "yes" (if supported) or "no" (if hallucinated),
       "feedback": "Identify the specific hallucinated sentence or write 'supported'."
    }}
    """),
    ("user", "Context: \n {documents} \n Generated answer: {answer}")
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