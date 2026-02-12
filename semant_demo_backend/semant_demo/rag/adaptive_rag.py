import openai
import langchain_google_genai 
from fastapi import HTTPException
from time import time

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from langchain_ollama import OllamaLLM

from langgraph.graph import StateGraph, START, END

from pydantic import BaseModel, Field

import logging
import re
import json
from datetime import datetime
import asyncio

from semant_demo.rag.rag_factory import BaseRag, register_rag_class
from semant_demo.config import Config
from semant_demo.schemas import SearchResponse, SearchRequest, RagRequest, RagResponse, AdaptiveRagState
from semant_demo.weaviate_search import WeaviateSearch
#import prompts from prompt file
from semant_demo.rag.adaptive_rag_prompts import *

DEBUG_PRINT = True

#graders
#grade relevancy of retrived documents
class GraderChunkRelevance(BaseModel):
    binary_score: str = Field(description="Documents are relevant to the question, 'yes' or 'no'")

#grade relevancy of the answer
class GraderAnswerRelevance(BaseModel):
    binary_score: str = Field(description="Is an answer base on the context, 'yes' or 'no'")

@register_rag_class
class AdaptiveRagGenerator(BaseRag):
    def __init__(self, global_config: Config, param_config):
        super().__init__(global_config, param_config)
        self.searcher = None
        #this can be part of config in future
        self.main_prompt = ChatPromptTemplate.from_messages(answer_question_prompt_template)
        self.history_prompt = ChatPromptTemplate.from_messages(refrase_question_from_history_prompt_template)
        self.extract_prompt = ChatPromptTemplate.from_messages(extract_metadata_from_question_template)
        self.multiquery_prompt = ChatPromptTemplate.from_messages(multiquery_prompt_template)
        self.hyde_prompt = ChatPromptTemplate.from_messages(hyde_prompt_template)
        self.context_grader_prompt = ChatPromptTemplate.from_messages(context_grader_prompt_template)
        self.output_parser = StrOutputParser()
        #create model instance (maybe create different model to different tasks in the future)
        model_type = param_config.get("model_type")
        self.model_type = model_type
        api_key = param_config.get("api_key", None)
        model_name = param_config.get("model_name", None)
        temperature = param_config.get("temperature", None)
        self.model = self._create_model(model_type, model_name, api_key, temperature)

        #extract metadata model
        self.extract_model = self._create_extract_model()

        #search parameters
        self.chunk_limit = param_config.get("chunk_limit", 5)
        self.alpha = param_config.get("alpha", 0.5)
        self.search_type = param_config.get("search_type", "hybrid")
        #load and build graph
        #load
        self.qt_strategy = param_config.get("qt_strategy", "multi_query") #step_back / hyde / multi_query / nothing
        self.max_retries = param_config.get("max_retries", 3)
        self.web_search_enabled = param_config.get("web_search_enabled", False)
        self.metadata_extraction_allowed = param_config.get("metadata_extraction_allowed", True)
        #build
        self.workflow = self._build_rag()
        self.rag = self.workflow.compile()

#--- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---

    # initialize model
    def _create_model(self, model_type: str, model_name: str, api_key: str, temperature: float):
        if temperature:
            temperature = temperature
        else:
            temperature = 0.0
        if (temperature == None):
            temperature = self.global_config.MODEL_TEMPERATURE
        # select model
        if (model_type == "GOOGLE"):
            return ChatGoogleGenerativeAI(
                model = model_name if model_name else self.global_config.GOOGLE_MODEL,
                google_api_key = api_key if api_key else self.global_config.GOOGLE_API_KEY,
                temperature = temperature
            )
        elif (model_type == "OLLAMA"):
            return OllamaLLM(
                model = model_name if model_name else self.global_config.OLLAMA_MODEL,
                base_url = self.global_config.OLLAMA_URLS[0],
                temperature = temperature
            )
        else:       #OPENAI
            return ChatOpenAI(
                model = model_name if model_name else self.global_config.OPENAI_MODEL,
                api_key = api_key if api_key else self.global_config.OPENAI_API_KEY,
                temperature = temperature
            )
    
    def _create_extract_model(self):
        #TODO can add optional model to config
        return self.model

    # create the graph - TODO přidat odstranovani uzlu
    def _build_rag(self):
        #define nodes
        workflow = StateGraph(AdaptiveRagState)
        workflow.add_node("transform_history", self.node_history_transformation)
        workflow.add_node("extract_metadata", self.node_extract_metadata)
        workflow.add_node("multi_query", self.node_multi_query)
        workflow.add_node("retrieve", self.node_retrieve)
        workflow.add_node("grade_context", self.node_grade_context)
        workflow.add_node("generate", self.node_generate)
        workflow.add_node("web_search", self.node_web_search)

        #define edges
        workflow.add_edge(START, "transform_history")

        workflow.add_edge("transform_history", "extract_metadata")
        workflow.add_edge("transform_history", "multi_query")

        workflow.add_edge("extract_metadata", "retrieve")
        workflow.add_edge("multi_query", "retrieve")

        workflow.add_edge("retrieve", "grade_context")

        #conditional edges - cycles
        workflow.add_conditional_edges(
            "grade_context",
            self.after_context_grade,
            {
                "generate" : "generate",
                "web_search" : "web_search",
                "transform" : "transform_history"
            }
        )

        workflow.add_conditional_edges(
            "generate",
            self.node_grade_generation,
            {
                "supported": END,
                "not_supported": "generate"
            }
        )

        return workflow

#--- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---

    # creation of the chain
    def _create_chain(self, model, prompt):    
        return prompt | model | self.output_parser
    
    # function to get history prompt in desire format
    def _get_prompt_history(self, history: list):
        prompt_history = []
        for msg in history:
            if msg['role'] == 'user':
                prompt_history.append(HumanMessage(content=msg['content']))
            elif msg['role'] == 'assistant':
                prompt_history.append(AIMessage(content=msg['content']))
        return prompt_history
    
    #function that converts incomming search results to desired format
    def _format_weaviate_context(self, results: list[SearchResponse]) -> str:
        snippets = [
            f"[doc{i+1}]" + res.text.replace('\\n', ' ')
            for i, res in enumerate(results)
        ]
        return ("\n".join(snippets))
    
#--- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---

    async def node_retrieve(self, state: AdaptiveRagState):
        #get metadata
        metadata = state.get("metadata", {})

        #is used strategy hyde --> use document embedding instead of query embedding
        use_hyde_embedding = True if self.qt_strategy == "hyde" else False

        if (DEBUG_PRINT):
            print(f"Is used hyde embedding: {use_hyde_embedding}.")

        #load all question variants
        queries = state.get("queries", [])
        if not queries:
            queries = [state["question"]]

        #create db search request
        async def single_search(query):
            search_request = SearchRequest(
                query = query,
                type = self.search_type,
                hybrid_search_alpha = self.alpha,
                limit = self.chunk_limit,
                min_year = metadata.get("min_year"),
                max_year = metadata.get("max_year"),
                min_date = metadata.get("min_date"),
                max_date = metadata.get("max_date"),
                language = metadata.get("language"),
                tag_uuids = [],
                positive = False,
                automatic = False,
                is_hyde = use_hyde_embedding
            )
            if (DEBUG_PRINT):
                print(f"search_request: {search_request}")
            #call db search
            return await self.searcher.search(search_request)

        #call in parallel
        search_tasks = [single_search(query) for query in queries]
        search_responses = await asyncio.gather(*search_tasks)
        
        #remove duplicities and put it together
        unique_chunks = {}
        for response in search_responses:
            for chunk in response.results:
                chunk_id = getattr(chunk, "id", None)
                print(f"chunk id: {chunk_id}")
                if chunk_id not in unique_chunks:
                    unique_chunks[chunk_id] = chunk

        all_chunks = list(unique_chunks.values())

        counter_value = state.get("iteration_counter", 0) + 1

        return  {"documents" : all_chunks, 
                 "iteration_counter" : counter_value
                 }
    
    #rephrase question to search desired data in database
    async def node_history_transformation(self, state: AdaptiveRagState):
        if (state["history"]):
            #create desired chain
            chain = self._create_chain(model=self.model, prompt=self.history_prompt)

            #convert history into desired format
            prompt_history = self._get_prompt_history(state["history"])

            correct_question = await chain.ainvoke({
                "question_string" : state["question"],
                "prompt_history" : prompt_history
            })

            if (DEBUG_PRINT):
                print(f"Refrased question: {correct_question}")

            return {"question" : correct_question}
        else:
            return {"question" : state["question"]}

    async def node_extract_metadata(self, state: AdaptiveRagState):
        if (self.metadata_extraction_allowed == True):
            chain =  self._create_chain (model=self.extract_model, prompt=self.extract_prompt)
            result = await chain.ainvoke({"question_string" : state["question"]})
            clean_result = re.sub(r'```json|```', '', result).strip()
            if (DEBUG_PRINT):
                print(f"metadata_clean_result: {clean_result}")
            try:
                metadata = json.loads(clean_result)
                metadata_structured = {
                    "min_year" : int(metadata.get("min_year")) if metadata.get("min_year") else None,
                    "max_year" : int(metadata.get("max_year")) if metadata.get("max_year") else None,
                    "language" : metadata.get("language")
                }
                if (DEBUG_PRINT):
                    print(f"metadata_structured: {metadata_structured}")
                return {"metadata" : metadata_structured}
            except Exception:
                return {"metadata" : {}}
        else:
            return {"metadata" : {}}
    
    async def node_multi_query(self, state: AdaptiveRagState):
        if self.qt_strategy == "multi_query":
            if (DEBUG_PRINT):
                print(f"Multi query mode")
            
            chain = self._create_chain(model = self.model, prompt=self.multiquery_prompt)
            result_raw = await chain.ainvoke({"question_string" : state["question"]})
            queries = [
                q.strip().lstrip("0123456789.- ")
                for q in result_raw.split("\n")
                if q.strip()
            ]

            if state["question"] not in queries:
                queries.append(state["question"])

            if (DEBUG_PRINT):
                print(f"Queries: {queries}")

            return {"queries" : queries}
        elif self.qt_strategy == "hyde":
            if (DEBUG_PRINT):
                print(f"HyDe mode")

            chain = self._create_chain(model = self.model, prompt=self.hyde_prompt)
            hypothetical_doc = await chain.ainvoke({"question_string" : state["question"]})

            if (DEBUG_PRINT):
                print(f"Hypothetical doc (first 100 char): {hypothetical_doc[:100]}...")

            return {"queries" : [hypothetical_doc]}
        else:
            return {"queries" : [state["question"]]}

    async def node_grade_context(self, state: AdaptiveRagState):
        chain = self._create_chain(model=self.model, prompt=self.context_grader_prompt)

        filtered_documents = []
        # check every document
        for doc in state["documents"]:
            result_raw = await chain.ainvoke({
                "question_string" : state["question"],
                "document" : doc
            })

            clean_result = re.sub(r'```json|```', '', result_raw).strip()
            try:
                graded_doc = json.loads(clean_result)
                score = graded_doc.get("binary_score", "no").lower()
                if "yes" in score:
                    filtered_documents.append(doc)
            except Exception:
                filtered_documents.append(doc)

        #if relevant return this
        if (DEBUG_PRINT):
            print(f"Relevant documents number: {len(filtered_documents)}, original doc number: {len(state["documents"])}")
        return {"documents" : filtered_documents}
    
    def after_context_grade (self, state: AdaptiveRagState):
        #generate if there are relevant documents
        if (state["documents"]):
            return "generate"
        else:
            if (state.get("iteration_counter", 0) < self.max_retries) and (self.metadata_extraction_allowed == True):
                print(f"No documents found, transformig query. Turning metadata extraction OFF.")
                self.metadata_extraction_allowed = False
                return "transform"
            else:
                pass
                #TODO do something else?
        return "generate"

    # generate an answer
    async def node_generate(self, state: AdaptiveRagState):
        chain = self._create_chain(model=self.model, prompt=self.main_prompt)

        #join snippets
        final_context = self._format_weaviate_context(state["documents"])

        #get history in desired format
        prompt_history = self._get_prompt_history(state["history"])

        answer = await chain.ainvoke({
            "context_string" : final_context,
            "question_string" : state["question"],
            "prompt_history" : prompt_history
        })

        if (DEBUG_PRINT):
            print(f"rag answer: {answer}")

        return {"generation": answer}
    
    def node_grade_generation (self, state: AdaptiveRagState):
        #TODO
        #if good
        return "supported"
        #else return "not_supported"
    
    def node_web_search (self, state: AdaptiveRagState):
        #TODO
        web_results = []
        return {"documents" : state["documents"] + web_results}
    
    #--- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---

    #method that is implemented in base rag class - basicly just preprocessing of request and calling generate method
    async def rag_request(self, request: RagRequest, searcher: WeaviateSearch) -> RagResponse:
        if (self.searcher == None):
            self.searcher = searcher
        if request.history:
            history_preprocessed = [msg.model_dump() for msg in request.history]
        else:
            history_preprocessed = []

        # call model
        try:
            t1 = time()

            intial_state_values = {
                "question" : request.question,
                "queries" : [],
                "history": history_preprocessed,
                "documents": [],
                "metadata": {},
                "iteration_counter": 0
            }
            
            config = {"recursion_limit" : 20}

            generated_result = await self.rag.ainvoke(intial_state_values, config=config)

            time_spent = time() - t1

        except (openai.AuthenticationError, langchain_google_genai.chat_models.ChatGoogleGenerativeAIError) as e:
            logging.warning(e)
            raise HTTPException(status_code=401, detail="Invalid API key.")
        except Exception as e:
            logging.error(f"RAG error: calling model {self.model_type}: {e}")
            raise HTTPException(status_code=503, detail="RAG error: Service is not avalaible.")

        # answer
        return RagResponse(
            rag_answer=generated_result["generation"].strip(),
            sources=generated_result["documents"],
            time_spent=time_spent
        )