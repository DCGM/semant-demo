from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
    ToolMessage
)
from langchain_core.tools import tool
from openai import AsyncOpenAI
import time
import json
import uuid
from typing import Dict, List, Any


from semant_demo.rag.rag_factory import BaseRag, register_rag_class
from semant_demo.config import Config
from semant_demo.weaviate_search import WeaviateSearch
from semant_demo.schemas import SearchResponse, SearchRequest, SearchType, RagSearch, RagRequest, RagResponse


IMPROVED_RAG_SYSTEM_PROMPT = """
You are a STRICT Agentic Retrieval-Augmented Generation (RAG) agent with strategic tool usage.

AVAILABLE TOOLS & WHEN TO USE THEM:

1. weaviate_search(query: str)
   USE WHEN: You need to retrieve documents from the vector database
   - Initial query processing → search immediately
   - After assess_retrieval_quality suggests retry → search with new query from expand_query

2. assess_retrieval_quality(question: str, retrieved_documents: str)
   USE WHEN: You have retrieved documents and need to check if they answer the question
   - IMMEDIATELY after weaviate_search, BEFORE attempting to answer
   - Returns: relevance_score (0-1), coverage (complete/partial/none), should_retry (bool)
   - Scores >= 0.6 → Proceed to answer
   - Scores < 0.6 → Call expand_query for alternatives

3. expand_query(original_query: str, context: str)
   USE WHEN: assess_retrieval_quality shows low scores or YOU want alternative search angles
   - context: "too_specific", "too_general", or "no_results"
   - Returns: list of alternative query formulations
   - Use top alternative with weaviate_search

4. decompose_question(question: str)
   USE WHEN: The question has multiple distinct parts or asks about cause-and-effect
   - Examples: "What is X and how does it affect Y?"
   - Returns: sub_queries list for searching separately
   - Search each sub-query, then synthesize results

5. synthesize_evidence(question: str, retrieved_documents: str)
   USE WHEN: You have good quality retrieval and need to generate final answer
   - Consolidates information across documents
   - Detects contradictions
   - Provides consolidated answer with proper citations

STRICT RULES:
1) You CANNOT answer without retrieving relevant context first via weaviate_search
2) You MUST use ONLY retrieved context in your answer
3) MANDATORY CITATIONS: Every sentence MUST end with [doc X]
4) MULTIPLE SOURCES: If claiming multiple docs support a statement, cite them: [doc 1], [doc 2]
5) Response language MUST match the user's question language
6) Use Markdown formatting for clarity

AGENT STRATEGY:
Step 1: Receive question
Step 2: Decide: Is question clear? → If vague, consider decompose_question first
Step 3: Call weaviate_search with initial question
Step 4: IMMEDIATELY call assess_retrieval_quality on results
Step 5: Based on assessment:
   - If coverage >= partial AND relevance_score >= 0.6 → Proceed to answer
   - If coverage == none OR relevance_score < 0.6 → Call expand_query, get alternatives, try new search
   - If multiple question parts → Call decompose_question, search each part separately
Step 6: Once quality is acceptable OR you've exhausted alternatives → Call synthesize_evidence for final answer
Step 7: Provide final answer with proper citations, if unable to fully answer the question, answer it partially and disclose it is not an complete answer.

ITERATION BUDGET: You have {remaining_iterations} iterations remaining.
Count carefully: search=2 step, assess=1 step, expand=1 step, decompose=1 step, synthesize=1 step

FAILURE RECOVERY:
- assess_retrieval_quality returns coverage="none"?
  → Try expand_query with context="no_results"
- Still no good results after expand_query?
  → Question might not be answerable from current KB
  → Check with decompose_question if it's multi-part
  → If all attempts exhausted, respond with final answer or:
  → "Sorry, I can´t answer the question."

IMPORTANT: Do NOT guess or use external knowledge. ONLY use retrieved documents or fall back to refuse.
"""

def extract_text_from_openai_message(msg):
    if isinstance(msg.content, str):
        return msg.content

    if isinstance(msg.content, list):
        texts = []
        for part in msg.content:
            if isinstance(part, dict) and part.get("type") == "text":
                texts.append(part.get("text", ""))
        return "".join(texts)

    return ""


def lc_messages_to_openai(messages):
    openai_msgs = []

    for m in messages:
        if isinstance(m, SystemMessage):
            role = "system"
            msg = {
                "role": role,
                "content": m.content
            }

        elif isinstance(m, HumanMessage):
            role = "user"
            msg = {
                "role": role,
                "content": m.content
            }

        elif isinstance(m, AIMessage):
            role = "assistant"
            msg = {
                "role": role,
                "content": m.content or ""
            }
            if "tool_calls" in m.additional_kwargs:
                msg["tool_calls"] = m.additional_kwargs["tool_calls"]

        elif isinstance(m, ToolMessage):
            role = "tool"
            msg = {
                "role": role,
                "content": m.content,
                "tool_call_id": m.tool_call_id
            }

        else:
            raise ValueError(f"Unknown message type: {type(m)}")

        openai_msgs.append(msg)

    return openai_msgs




class LangchainLLM:
    def __init__(self, model: str):
        self.client = AsyncOpenAI()
        self.model = model

    async def invoke(self, messages: list, temperature: float = 0.6):
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=lc_messages_to_openai(messages),
            temperature=temperature,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "weaviate_search",
                        "description": "Search relevant documents in a vector database",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string"}
                            },
                            "required": ["query"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "assess_retrieval_quality",
                        "description": "Assess if retrieved documents answer the question. Returns JSON with relevance_score, coverage, missing_aspects.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "question": {"type": "string"},
                                "retrieved_documents": {"type": "string"}
                            },
                            "required": ["question", "retrieved_documents"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "expand_query",
                        "description": "Generate alternative query formulations for better retrieval when initial search fails",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "original_query": {"type": "string"},
                                "context": {"type": "string", "enum": ["too_specific", "too_general", "no_results"]}
                            },
                            "required": ["original_query", "context"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "decompose_question",
                        "description": "Decompose multi-part questions into separate sub-queries",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "question": {"type": "string"}
                            },
                            "required": ["question"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "synthesize_evidence",
                        "description": "Synthesize evidence from retrieved documents into a coherent answer with citations and detect contradictions",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "question": {"type": "string"},
                                "retrieved_documents": {"type": "string"}
                            },
                            "required": ["question", "retrieved_documents"]
                        }
                    }
                }
            ],
        )
        return response.choices[0].message


class WeaviateToolWrapper:
    def __init__(self, searcher: WeaviateSearch, rag_search: RagSearch, alpha: float, chunk_limit: int):
        self.searcher = searcher
        self.rag_search = rag_search
        self.alpha = alpha
        self.chunk_limit = chunk_limit
        self.last_results = None 

    async def _call_weaviate_search(self, rag_search: RagSearch,  type: SearchType) -> SearchResponse:
        #create db search request
        search_request = SearchRequest(
            query = rag_search.search_query,
            type = type,
            hybrid_search_alpha = self.alpha,
            limit = self.chunk_limit,
            min_year = rag_search.min_year,
            max_year = rag_search.max_year,
            min_date = rag_search.min_date,
            max_date = rag_search.max_date,
            language = rag_search.language,
            tag_uuids = [],
            positive = False,
            automatic = False
        )

        search_response = await self.searcher.search(search_request)
        return search_response

    # @tool
    async def weaviate_search(self, query: str) -> str:
        # print("Searching...")
        self.rag_search.search_query = query

        response = await self._call_weaviate_search(
            self.rag_search,
            self.rag_search.search_type
        )

        self.last_results = response.results

        # texts = [hit.text for hit in response.results]
        formatted_chunks = []

        for i, hit in enumerate(response.results, start=1):
            formatted_chunks.append(f"[doc {i}] {hit.text}")

        return "\n\n".join(formatted_chunks)


class AssessRetrievalQualityTool:
    def __init__(self, model: str):
        self.client = AsyncOpenAI()
        self.model = model

    async def assess_retrieval_quality(self, question: str, retrieved_documents: str) -> str:
        """
        Assesses whether retrieved documents answer the question.
        Returns JSON with relevance_score, coverage, and should_retry flag.
        """
        system_prompt = """
You are a retrieval quality assessment expert.

Analyze if the retrieved documents answer the given question.

Provide a JSON response with:
{
  "relevance_score": <float 0-1>,
  "coverage": "<complete|partial|none>",
  "missing_aspects": [<list of what's missing>],
  "should_retry": <bool>,
  "reasoning": "<brief explanation>"
}

Guidelines:
- relevance_score >= 0.6 and coverage >= partial = good retrieval
- relevance_score < 0.6 or coverage = none = poor retrieval, should_retry = true
- List specific gaps if coverage is partial
- Be strict: only mark complete if documents fully address the question
"""

        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=0.3,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Question: {question}\n\nRetrieved Documents:\n{retrieved_documents}"}
            ],
        )

        return response.choices[0].message.content.strip()


class ExpandQueryTool:
    def __init__(self, model: str):
        self.client = AsyncOpenAI()
        self.model = model

    async def expand_query(self, original_query: str, context: str) -> str:
        """
        Generates alternative query formulations for better retrieval.
        Context indicates why alternative is needed: "too_specific", "too_general", "no_results"
        """
        system_prompt = """
You are a query expansion specialist for semantic search.

Given an original query and a context indicating why it needs improvement,
generate 3-5 alternative query formulations that might better match relevant documents.
These alternative queries have to be in the same language as the original query.

Context meanings:
- "too_specific": Original query too narrow, needs broader formulations
- "too_general": Original query too broad, needs more specific angles
- "no_results": Original query retrieves nothing, needs completely different angles

Provide JSON response:
{
  "alternatives": ["query1", "query2", "query3", ...],
  "reasoning": "<brief explanation of why these alternatives help>"
}

Return ONLY the JSON, no other text.
Focus on semantic variations and synonyms, not just word replacements.
"""

        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=0.7,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Original Query: {original_query}\nContext: {context}"}
            ],
        )

        return response.choices[0].message.content.strip()


class DecomposeQuestionTool:
    def __init__(self, model: str):
        self.client = AsyncOpenAI()
        self.model = model

    async def decompose_question(self, question: str) -> str:
        """
        Decomposes multi-part questions into separate sub-queries for targeted searching.
        """
        system_prompt = """
You are a question decomposition expert.

Analyze the question to identify if it has multiple distinct parts or asks about relationships.

Provide JSON response:
{
  "is_multi_part": <bool>,
  "num_parts": <int>,
  "sub_queries": ["sub_q1", "sub_q2", ...],
  "reasoning": "<explanation of decomposition>",
  "suggested_strategy": "<how to combine answers>"
}

Examples of multi-part questions:
- "How is X made and what are its uses?" → 2 parts
- "Why did X happen and what were the consequences?" → 2 parts
- "What is X, how does it compare to Y, and when should it be used?" → 3 parts

Return ONLY the JSON, no other text.
If not multi-part, set is_multi_part=false and sub_queries=[].
"""

        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=0.5,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
        )

        return response.choices[0].message.content.strip()


class SynthesizeEvidenceTool:
    def __init__(self, model: str):
        self.client = AsyncOpenAI()
        self.model = model

    async def synthesize_evidence(self, question: str, retrieved_documents: str) -> str:
        """
        Synthesizes evidence from retrieved documents into a coherent answer with citations.
        Consolidates key information in the same language as the question.
        """
        system_prompt = """
You are an evidence synthesis expert for RAG systems.

Your task:
1. Consolidate information from the retrieved documents
2. Generate a comprehensive answer with proper citations

Requirements:
- EVERY sentence MUST end with [doc X] citation
- If multiple docs support a claim, cite them: [doc 1], [doc 2]
- Use Markdown formatting
- Do NOT add information not in the documents
- RESPOND IN THE SAME LANGUAGE AS THE QUESTION
- Output ONLY the consolidated answer with citations - nothing else

Do NOT include:
- Sections about contradictions
- Confidence levels
- Any explanatory text beyond the answer itself
"""

        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Question: {question}\n\nRetrieved Documents:\n{retrieved_documents}"}
            ],
        )

        return response.choices[0].message.content.strip()

@register_rag_class
class xmartiAgentRag(BaseRag):

    def __init__(self, global_config: Config, param_config):
        super().__init__(global_config, param_config)
        self.model_type = param_config.get("model_name", "gpt-4o-mini")
        self.llm = LangchainLLM(self.model_type)
        self.search_type = param_config.get("search_type")
        self.alpha = param_config.get("alpha")
        self.chunk_limit = param_config.get("chunk_limit")
        self.agent_iterations = param_config.get("agent_iterations", 7)


    async def rag_request(
        self,
        request: RagRequest,
        searcher: WeaviateSearch
    ) -> RagResponse:

        start_time = time.perf_counter()

        # Tool init
        iteration_limit = self.agent_iterations  # Use the configured number of agent iterations
        weaviate_tool = WeaviateToolWrapper(
            searcher=searcher,
            rag_search=request.rag_search,
            alpha=self.alpha,
            chunk_limit=self.chunk_limit
        )
        assess_tool = AssessRetrievalQualityTool(self.model_type)
        expand_tool = ExpandQueryTool(self.model_type)
        decompose_tool = DecomposeQuestionTool(self.model_type)
        synthesize_tool = SynthesizeEvidenceTool(self.model_type)

        retrieved_sources = []

        # Initialize all new tools


        tools = {
            "weaviate_search": weaviate_tool.weaviate_search,
            "assess_retrieval_quality": assess_tool.assess_retrieval_quality,
            "expand_query": expand_tool.expand_query,
            "decompose_question": decompose_tool.decompose_question,
            "synthesize_evidence": synthesize_tool.synthesize_evidence,
        }

        messages = [
            SystemMessage(
                content=IMPROVED_RAG_SYSTEM_PROMPT.format(remaining_iterations=iteration_limit)
            ),
            HumanMessage(content=request.question)
        ]

        last_tool_called = None  # Track the last tool called

        for i in range(iteration_limit):

            # Use higher temperature for reasoning, lower for final answer
            temperature = 0.6 if i < iteration_limit - 1 else 0.2

            ai_msg = await self.llm.invoke(messages, temperature=temperature)
            print(f"LLM response at iteration {i+1}:\nTool Calls: {ai_msg.tool_calls}\n{'-'*50}")

            # 🔹 CASE 1 — model wants to call a tool
            if getattr(ai_msg, "tool_calls", None):

                tool_call = ai_msg.tool_calls[0]
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                # Track the last tool called
                last_tool_called = tool_name

                tool_fn = tools.get(tool_name)
                if tool_fn is None:
                    raise ValueError(f"Unknown tool {tool_name}")

                # Add assistant message WITH tool call metadata
                messages.append(
                    AIMessage(
                        content="",
                        additional_kwargs={
                            "tool_calls": [tool_call]
                        }
                    )
                )

                # Call tool
                observation = await tool_fn(**tool_args)

                # Handle different tool responses
                if tool_name == "weaviate_search":
                    retrieved_sources = weaviate_tool.last_results or []
                    # Add tool response
                    messages.append(
                        ToolMessage(
                            tool_call_id=tool_call.id,
                            content=observation
                        )
                    )

                elif tool_name == "assess_retrieval_quality":
                    # Pass assessment to agent for decision making
                    messages.append(
                        ToolMessage(
                            tool_call_id=tool_call.id,
                            content=observation
                        )
                    )

                    # Check if assessment indicates good retrieval quality
                    # If so, signals to agent that it should proceed to synthesis instead of more searches
                    try:
                        assessment_obj = json.loads(observation)
                        relevance_score = assessment_obj.get("relevance_score", 0)
                        coverage = assessment_obj.get("coverage", "none")

                        # If assessment is good, add guidance message to encourage synthesis
                        if relevance_score >= 0.65 and coverage in ["complete", "partial"]:
                            messages.append(
                                AIMessage(
                                    content="Assessment shows good quality retrieval. I should now generate the final answer using synthesize_evidence."
                                )
                            )
                    except (json.JSONDecodeError, ValueError):
                        # If parsing fails, let agent decide normally
                        pass

                elif tool_name in ["expand_query", "decompose_question"]:
                    # These tools return structured info for the agent to use
                    messages.append(
                        ToolMessage(
                            tool_call_id=tool_call.id,
                            content=observation
                        )
                    )

                elif tool_name == "synthesize_evidence":
                    # This should be the final answer generation
                    messages.append(
                        ToolMessage(
                            tool_call_id=tool_call.id,
                            content=observation
                        )
                    )


                else:
                    messages.append(
                        ToolMessage(
                            tool_call_id=tool_call.id,
                            content=observation
                        )
                    )
                if tool_name != "weaviate_search":
                    print(f"Tool response for {tool_name}:\n{observation}\n{'-'*50}")

                continue

            final_answer = extract_text_from_openai_message(ai_msg)

            return RagResponse(
                response_id = str(uuid.uuid4()),
                rag_answer=final_answer,
                sources=weaviate_tool.last_results or [],
                time_spent=time.perf_counter() - start_time
            )


        # Final attempt: if last tool was weaviate_search, try to answer with available results
        if last_tool_called == "weaviate_search" and retrieved_sources:
            # print("Attempting final answer synthesis from last search results...")

            # Format the retrieved sources for assessment
            formatted_chunks = []
            for i, hit in enumerate(retrieved_sources[:5], start=1):
                formatted_chunks.append(f"[doc {i}] {hit.text}")
            retrieved_docs_text = "\n\n".join(formatted_chunks)

            try:
                # Assess the retrieval quality one last time
                assessment = await assess_tool.assess_retrieval_quality(
                    request.question,
                    retrieved_docs_text
                )
                # print(f"Final assessment: {assessment}\nType: {type(assessment)}\n{'-'*50}")

                # Parse assessment score and only generate answer if quality is acceptable
                try:
                    assessment_obj = json.loads(assessment)
                    relevance_score = assessment_obj.get("relevance_score", 0)
                    coverage = assessment_obj.get("coverage", "none")

                    # Only generate answer if assessment meets quality threshold
                    if relevance_score >= 0.5 and coverage != "none":
                        # Try to synthesize evidence from the retrieved documents
                        final_synthesis = await synthesize_tool.synthesize_evidence(
                            request.question,
                            retrieved_docs_text
                        )
                        # print(f"Final synthesis: {final_synthesis}\n{'-'*50}")

                        return RagResponse(
                            response_id=str(uuid.uuid4()),
                            rag_answer=final_synthesis,
                            sources=weaviate_tool.last_results or [],
                            time_spent=time.perf_counter() - start_time
                        )
                    else:
                        # Assessment indicates poor retrieval quality
                        return RagResponse(
                            response_id=str(uuid.uuid4()),
                            rag_answer="Sorry, I can´t answer the question based on the retrieved information.",
                            sources=weaviate_tool.last_results or [],
                            time_spent=time.perf_counter() - start_time
                        )
                except json.JSONDecodeError:
                    # If assessment JSON parsing fails, fall back to synthesizing anyway
                    final_synthesis = await synthesize_tool.synthesize_evidence(
                        request.question,
                        retrieved_docs_text
                    )
                    return RagResponse(
                        response_id=str(uuid.uuid4()),
                        rag_answer=final_synthesis,
                        sources=weaviate_tool.last_results or [],
                        time_spent=time.perf_counter() - start_time
                    )
            except Exception as e:
                print(f"Error during final synthesis: {e}")
                # Fall through to default response if synthesis fails

        # Fallback if loop ends without final answer
        return RagResponse(
            response_id = str(uuid.uuid4()),
            rag_answer="Sorry, I can´t answer the question based on the retrieved information.",
            sources=[],
            time_spent=time.perf_counter() - start_time
        )
