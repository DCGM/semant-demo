from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
    ToolMessage
)
from langchain_core.language_models import BaseChatModel
import time
import json
import uuid


from semant_demo.adapters.llm.gateway import message_text
from semant_demo.adapters.llm.models import Capability
from semant_demo.rag.rag_factory import BaseRag, register_rag_class
from semant_demo.config import Config
from semant_demo.features.search.service import Retriever
from semant_demo.features.search.schemas import SearchResponse, SearchRequest, SearchType
from semant_demo.features.rag.schemas import RagSearch, RagRequest, RagResponse


# Tools the agent model may call (OpenAI function format).
AGENT_TOOLS = [
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
]


class WeaviateToolWrapper:
    def __init__(self, retrieve: Retriever, rag_search: RagSearch, alpha: float, chunk_limit: int):
        self.retrieve = retrieve
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

        search_response = await self.retrieve(search_request)
        return search_response

    # @tool
    async def weaviate_search(self, query: str) -> str:
        self.rag_search.search_query = query

        response = await self._call_weaviate_search(
            self.rag_search,
            self.rag_search.search_type
        )

        self.last_results = response.results

        formatted_chunks = []

        for i, hit in enumerate(response.results, start=1):
            formatted_chunks.append(f"[doc {i}] {hit.text}")

        return "\n\n".join(formatted_chunks)


class AssessRetrievalQualityTool:
    def __init__(self, model: BaseChatModel, system_prompt: str):
        self.model = model
        self.system_prompt = system_prompt

    async def assess_retrieval_quality(self, question: str, retrieved_documents: str) -> str:
        """
        Assesses whether retrieved documents answer the question.
        Returns JSON with relevance_score, coverage, and should_retry flag.
        """
        response = await self.model.ainvoke([
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=f"Question: {question}\n\nRetrieved Documents:\n{retrieved_documents}"),
        ])

        return message_text(response.content).strip()


class ExpandQueryTool:
    def __init__(self, model: BaseChatModel, system_prompt: str):
        self.model = model
        self.system_prompt = system_prompt

    async def expand_query(self, original_query: str, context: str) -> str:
        """
        Generates alternative query formulations for better retrieval.
        Context indicates why alternative is needed: "too_specific", "too_general", "no_results"
        """
        response = await self.model.ainvoke([
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=f"Original Query: {original_query}\nContext: {context}"),
        ])

        return message_text(response.content).strip()


class DecomposeQuestionTool:
    def __init__(self, model: BaseChatModel, system_prompt: str):
        self.model = model
        self.system_prompt = system_prompt

    async def decompose_question(self, question: str) -> str:
        """
        Decomposes multi-part questions into separate sub-queries for targeted searching.
        """
        response = await self.model.ainvoke([
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=question),
        ])

        return message_text(response.content).strip()


class SynthesizeEvidenceTool:
    def __init__(self, model: BaseChatModel, system_prompt: str):
        self.model = model
        self.system_prompt = system_prompt

    async def synthesize_evidence(self, question: str, retrieved_documents: str) -> str:
        """
        Synthesizes evidence from retrieved documents into a coherent answer with citations.
        Consolidates key information in the same language as the question.
        """
        response = await self.model.ainvoke([
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=f"Question: {question}\n\nRetrieved Documents:\n{retrieved_documents}"),
        ])

        return message_text(response.content).strip()

@register_rag_class
class xmartiAgentRag(BaseRag):

    def __init__(self, global_config: Config, param_config, llm=None):
        super().__init__(global_config, param_config, llm)
        # The agent runs at 0.3, its last iteration at 0.2; each tool subcall has its own temperature.
        self.agent_model = self.chat_model(temperature=0.3, requires=(Capability.tools,)).bind_tools(AGENT_TOOLS)
        self.final_agent_model = self.chat_model(temperature=0.2, requires=(Capability.tools,)).bind_tools(AGENT_TOOLS)
        self.assess_model = self.chat_model(temperature=0.3)
        self.expand_model = self.chat_model(temperature=0.7)
        self.decompose_model = self.chat_model(temperature=0.5)
        self.synthesize_model = self.chat_model(temperature=0.2)
        self.search_type = param_config.get("search_type")
        self.alpha = param_config.get("alpha")
        self.chunk_limit = param_config.get("chunk_limit")
        self.agent_iterations = param_config.get("agent_iterations", 7)
        prompts = param_config.get("prompts", {})
        self.system_prompt_template = prompts.get("system_prompt_template")
        self.assess_prompt = prompts.get("assess_retrieval_quality_prompt")
        self.expand_prompt = prompts.get("expand_query_prompt")
        self.decompose_prompt = prompts.get("decompose_question_prompt")
        self.synthesize_prompt = prompts.get("synthesize_evidence_prompt")


    async def rag_request(
        self,
        request: RagRequest,
        retrieve: Retriever
    ) -> RagResponse:

        start_time = time.perf_counter()

        # Tool init
        iteration_limit = self.agent_iterations  # Use the configured number of agent iterations
        weaviate_tool = WeaviateToolWrapper(
            retrieve=retrieve,
            rag_search=request.rag_search,
            alpha=self.alpha,
            chunk_limit=self.chunk_limit
        )
        assess_tool = AssessRetrievalQualityTool(self.assess_model, self.assess_prompt)
        expand_tool = ExpandQueryTool(self.expand_model, self.expand_prompt)
        decompose_tool = DecomposeQuestionTool(self.decompose_model, self.decompose_prompt)
        synthesize_tool = SynthesizeEvidenceTool(self.synthesize_model, self.synthesize_prompt)

        retrieved_sources = []


        tools = {
            "weaviate_search": weaviate_tool.weaviate_search,
            "assess_retrieval_quality": assess_tool.assess_retrieval_quality,
            "expand_query": expand_tool.expand_query,
            "decompose_question": decompose_tool.decompose_question,
            "synthesize_evidence": synthesize_tool.synthesize_evidence,
        }

        messages = [
            SystemMessage(
                content=self.system_prompt_template.format(remaining_iterations=iteration_limit)
            ),
            HumanMessage(content=request.question)
        ]

        for i in range(iteration_limit):

            # Use low temperature for consistent, focused tool usage
            agent_model = self.agent_model if i < iteration_limit - 1 else self.final_agent_model

            ai_msg = await agent_model.ainvoke(messages)
            print(f"LLM response at iteration {i+1}:\nTool Calls: {ai_msg.tool_calls}\n{'-'*50}")

            # 🔹 CASE 1 — model wants to call a tool
            if getattr(ai_msg, "tool_calls", None):

                tool_call = ai_msg.tool_calls[0]
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]


                tool_fn = tools.get(tool_name)
                if tool_fn is None:
                    raise ValueError(f"Unknown tool {tool_name}")

                # Add assistant message WITH tool call metadata
                messages.append(
                    AIMessage(
                        content="",
                        tool_calls=[tool_call]
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
                            tool_call_id=tool_call["id"],
                            content=observation
                        )
                    )

                elif tool_name == "assess_retrieval_quality":
                    # Pass assessment to agent for decision making
                    messages.append(
                        ToolMessage(
                            tool_call_id=tool_call["id"],
                            content=observation
                        )
                    )

                    # Check if assessment indicates any retrieval quality
                    # If so, strongly guide agent to proceed to synthesis
                    try:
                        assessment_obj = json.loads(observation)
                        relevance_score = assessment_obj.get("relevance_score", 0)
                        coverage = assessment_obj.get("coverage", "none")

                        # If assessment shows any relevant content, push toward synthesis
                        if relevance_score >= 0.3 and coverage in ["complete", "partial"]:
                            messages.append(
                                AIMessage(
                                    content="Assessment shows relevant retrieval. I should now generate the final answer using synthesize_evidence. A partial answer is better than no answer."
                                )
                            )
                        elif retrieved_sources:
                            # Even if assessment is low, if we have sources, encourage answering
                            messages.append(
                                AIMessage(
                                    content="Even though assessment scores are low, I have retrieved documents. I should attempt to answer using synthesize_evidence rather than refusing."
                                )
                            )
                    except (json.JSONDecodeError, ValueError):
                        # If parsing fails, encourage synthesis if we have sources
                        if retrieved_sources:
                            messages.append(
                                AIMessage(
                                    content="Assessment parsing failed, but I have retrieved documents. I should attempt to answer using synthesize_evidence."
                                )
                            )

                elif tool_name in ["expand_query", "decompose_question"]:
                    # These tools return structured info for the agent to use
                    messages.append(
                        ToolMessage(
                            tool_call_id=tool_call["id"],
                            content=observation
                        )
                    )

                elif tool_name == "synthesize_evidence":
                    # This should be the final answer generation
                    messages.append(
                        ToolMessage(
                            tool_call_id=tool_call["id"],
                            content=observation
                        )
                    )


                else:
                    messages.append(
                        ToolMessage(
                            tool_call_id=tool_call["id"],
                            content=observation
                        )
                    )
                # if tool_name != "weaviate_search":
                #     print(f"Tool response for {tool_name}:\n{observation}\n{'-'*50}")

                continue

            final_answer = message_text(ai_msg.content)

            # print("Returning final answer normally:", final_answer)

            return RagResponse(
                response_id = str(uuid.uuid4()),
                rag_answer=final_answer,
                sources=weaviate_tool.last_results or [],
                time_spent=time.perf_counter() - start_time
            )


        # Final attempt: if we have ANY retrieved sources, always try to synthesize an answer
        if retrieved_sources:
            formatted_chunks = []
            for i, hit in enumerate(retrieved_sources[:5], start=1):
                formatted_chunks.append(f"[doc {i}] {hit.text}")
            retrieved_docs_text = "\n\n".join(formatted_chunks)

            try:
                final_synthesis = await synthesize_tool.synthesize_evidence(
                    request.question,
                    retrieved_docs_text
                )

                print("Returning final answer after synthesis:", final_synthesis)
                return RagResponse(
                    response_id=str(uuid.uuid4()),
                    rag_answer=final_synthesis,
                    sources=weaviate_tool.last_results or [],
                    time_spent=time.perf_counter() - start_time
                )
            except Exception as e:
                pass
                # print(f"Error during final synthesis: {e}")
                # Fall through to default response if synthesis fails

        # Fallback if loop ends without final answer AND no sources were retrieved
        return RagResponse(
            response_id = str(uuid.uuid4()),
            rag_answer="Sorry, I can´t answer the question based on the retrieved information.",
            sources=weaviate_tool.last_results or [],
            time_spent=time.perf_counter() - start_time
        )
