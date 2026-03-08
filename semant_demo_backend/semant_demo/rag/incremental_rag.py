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

#from langchain_community.tools import DuckDuckGoSearchRun   #Tavily can be used as well but it requires API key
from ddgs import DDGS
import uuid

from langgraph.graph import StateGraph, START, END

from pydantic import BaseModel, Field

import logging
import re
import json
from datetime import datetime
import asyncio

from semant_demo.rag.rag_factory import BaseRag, register_rag_class
from semant_demo.config import Config
from semant_demo.schemas import SearchResponse, SearchRequest, RagRequest, RagResponse, AdaptiveRagState, TextChunkWithDocument, Document, ExplainRequest
from semant_demo.weaviate_search import WeaviateSearch
#import prompts from prompt file
from semant_demo.rag.incremental_rag_prompts import *

DEBUG_PRINT = True

@register_rag_class
class IncrementalAdaptiveRagGenerator(BaseRag):
    def __init__(self, global_config: Config, param_config):
        super().__init__(global_config, param_config)
        self.searcher = None
        #this can be part of config in future
        self.main_prompt = ChatPromptTemplate.from_messages(answer_question_prompt_template)
        self.main_prompt_history = ChatPromptTemplate.from_messages(answer_question_with_history_prompt_template)
        self.history_prompt = ChatPromptTemplate.from_messages(refrase_question_from_history_prompt_template)
        self.extract_prompt = ChatPromptTemplate.from_messages(extract_metadata_from_question_template)
        self.multiquery_prompt = ChatPromptTemplate.from_messages(multiquery_prompt_template)
        self.hyde_prompt = ChatPromptTemplate.from_messages(hyde_prompt_template)
        self.context_grader_prompt = ChatPromptTemplate.from_messages(context_grader_prompt_template)
        self.generation_grader_prompt = ChatPromptTemplate.from_messages(generation_grader_prompt_template)
        self.check_sufficient_context_prompt = ChatPromptTemplate.from_messages(check_sufficient_context_prompt_template)
        self.explain_selected_text_prompt = ChatPromptTemplate.from_messages(explain_selected_text_prompt_template)
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
        self.additional_tries_with_web_search = param_config.get("additional_tries_with_web_search", 2)
        self.web_search_enabled = param_config.get("web_search_enabled", False)
        self.metadata_extraction_allowed = param_config.get("metadata_extraction_allowed", True)
        self.self_reflection = param_config.get("self_reflection", True)
        #build
        self.workflow = self._build_rag()
        self.rag = self.workflow.compile()

        if (DEBUG_PRINT == True):
            print("Adaptive RAG version 14")

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
    
     # create the graph
    def _build_rag(self):
        #define nodes
        workflow = StateGraph(AdaptiveRagState)
        workflow.add_node("transform_history", self.node_history_transformation)
        workflow.add_node("check_context", self.node_check_context)
        workflow.add_node("start_retrieval_branch", lambda state: state)
        workflow.add_node("extract_metadata", self.node_extract_metadata)
        workflow.add_node("multi_query", self.node_multi_query)
        workflow.add_node("retrieve", self.node_retrieve)
        workflow.add_node("grade_context", self.node_grade_context)
        workflow.add_node("generate", self.node_generate)
        workflow.add_node("grade_generation", self.node_grade_generation)
        workflow.add_node("web_search", self.node_web_search)

        #define edges
        workflow.add_edge(START, "transform_history")

        workflow.add_edge("transform_history", "check_context")

        workflow.add_edge("start_retrieval_branch", "multi_query")
        workflow.add_edge("start_retrieval_branch", "extract_metadata")

        workflow.add_edge("extract_metadata", "retrieve")
        workflow.add_edge("multi_query", "retrieve")

        workflow.add_edge("retrieve", "grade_context")

        workflow.add_edge("generate", "grade_generation")
        workflow.add_edge("web_search", "generate")

        #conditional edges - cycles
        workflow.add_conditional_edges(
            "check_context",
            self.decide_after_check,
            {
                "sufficient" : "generate",
                "insufficient" : "start_retrieval_branch"
            }
        )

        workflow.add_conditional_edges(
            "grade_context",
            self.after_context_grade,
            {
                "generate" : "generate",
                "web_search" : "web_search",
                "transform" : "start_retrieval_branch"
            }
        )

        workflow.add_conditional_edges(
            "grade_generation",
            self.decide_after_generation,
            {
                "finish": END,
                "retry" : "start_retrieval_branch"
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
    
    # function to extract important information from db doc
    def _get_clean_doc(self, doc) -> str:
        doc_info = doc.document_object
        title = getattr(doc_info, "title", "Unknown titel")
        year = getattr(doc_info, "yearIssued", "Unknown year")
        clean_doc = f"DOCUMENT/DOKUMENT: {title} (Year issued/Rok vydání: {year}) "
        clean_doc = clean_doc + f"CONTENT/OBSAH: " + str(doc.text.replace('\\n', ' '))

        return clean_doc

    #function that converts incomming search results to desired format
    def _format_weaviate_context(self, results: list[SearchResponse]) -> str:
        snippets = []
        for i, res in enumerate(results):
            clean_text = self._get_clean_doc(res)
            snippets.append(f"\n---SOURCE [doc{i+1}] START ---\n{clean_text}\n--- SOURCE [doc{i+1}] END ---")
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
                limit = 5 if state.get("retrieval_iteration_counter", 0) == 0 else self.chunk_limit,
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
        all_chunks = all_chunks[:10]

        counter_value = state.get("retrieval_iteration_counter", 0) + 1

        return  {"documents" : all_chunks, 
                 "retrieval_iteration_counter" : counter_value
                 }
    
    #rephrase question to search desired data in database
    async def node_history_transformation(self, state: AdaptiveRagState):
        if (state["history"]):
            #create desired chain
            chain = self._create_chain(model=self.model, prompt=self.history_prompt)

            #convert history into desired format
            prompt_history = self._get_prompt_history(state["history"])

            correct_question = await chain.ainvoke({
                "question_string" : state["original_question"],
                "prompt_history" : prompt_history
            })

            if (DEBUG_PRINT):
                print(f"Refrased question: {correct_question}")

            return {"question" : correct_question}
        else:
            return {"question" : state["original_question"]}
        
    async def node_check_context(self, state: AdaptiveRagState):
        if (state["history"] and state["documents"]):
            chain = self._create_chain(model=self.model, prompt=self.check_sufficient_context_prompt)
            context = self._format_weaviate_context(state["documents"])
            result  = await chain.ainvoke({
                "context_string" : context,
                "question_string" : state["question"]
            })
            print(f"Previous context grade result: {result}")
            if ("yes" in result.lower()):
                return {"context_sufficient" : True}

        return {"context_sufficient" : False}
            

    def decide_after_check(self, state: AdaptiveRagState):
        if (state["context_sufficient"] == True):
            if (DEBUG_PRINT):
                print(f"Previous context is sufficient, skipping DB search.")
            return "sufficient"
        else:
            if (DEBUG_PRINT):
                print(f"Starting  DB search.")
            return "insufficient"

    async def node_extract_metadata(self, state: AdaptiveRagState):
        return {"metadata" : {}}
        
    async def node_multi_query(self, state: AdaptiveRagState):
        iteration = state.get("retrieval_iteration_counter", 0)
        #first time try simple retrieve
        if (iteration == 0):
            return {"queries" : [state["question"]]}
        
        else:
            #multiple query generation
            if (DEBUG_PRINT):
                print(f"MULTI QUERY MODE")

            chain = self._create_chain(model = self.model, prompt = self.multiquery_prompt)
            result_raw = await chain.ainvoke({"question_string" : state["question"]})

            # simple parser
            queries = [line.strip().lstrip("0123456789.- ") for line in result_raw.split("\n") if len(line.strip()) > 5]
            queries = queries[:3]

            if state["question"] not in queries:
                    queries.append(state["question"])

            return {"queries" : queries}



    async def node_grade_context(self, state: AdaptiveRagState):
        return {"documents": state["documents"]}
    
    def after_context_grade (self, state: AdaptiveRagState):
        return "generate"

    # generate an answer
    async def node_generate(self, state: AdaptiveRagState):
        
        #join snippets
        final_context = self._format_weaviate_context(state["documents"])
        if (DEBUG_PRINT):
            print(f"DEBUG: Context length (chars): {len(final_context)}")

        if (state["history"]):
            chain = self._create_chain(model=self.model, prompt=self.main_prompt_history)
            #get history in desired format
            prompt_history = self._get_prompt_history(state["history"])

            answer = await chain.ainvoke({
                "context_string" : final_context,
                "original_question" : state["original_question"],
                "question_string" : state["question"],
                "prompt_history" : prompt_history
            })
        else:
            chain = self._create_chain(model=self.model, prompt=self.main_prompt)
            answer = await chain.ainvoke({
                "context_string" : final_context,
                "question_string" : state["question"]
            })

        if (DEBUG_PRINT):
            print(f"rag answer: {answer}")

        return {"generation": answer}
    
    async def node_grade_generation (self, state: AdaptiveRagState):
        gen_value = state.get("generation_iteration_counter", 0) + 1
        chain = self._create_chain(model=self.model, prompt=self.generation_grader_prompt)

        #this is grading base on question and answer --> should effect answer relevancy metrics and maybe context recall/precision
        try:
            result_raw = await chain.ainvoke({
                "question": state["question"],
                "answer": state["generation"]
            })
            clean_result = re.sub(r'```json|```', '', result_raw).strip()
            decision = json.loads(clean_result)
            
            if decision.get("is_complete") == "no":
                if (DEBUG_PRINT):
                    print("GRADE GENERATION: Answer incomplete. Routing to Retry.")
                return {"feedback": "insufficient", "generation_iteration_counter": gen_value}
            else:
                return {"feedback": "supported", "generation_iteration_counter": gen_value}
            
        except Exception as e:
            if (DEBUG_PRINT): 
                print(f"GRADER ERROR: {e}. Defaulting to finish.")
            return {"feedback": "supported", "generation_iteration_counter": gen_value}

    def decide_after_generation (self, state: AdaptiveRagState):
        if state["feedback"] == "supported" or state["retrieval_iteration_counter"] >= self.max_retries:
            if (DEBUG_PRINT): 
                print("FINISHING: Answer satisfactory or max retries reached.")
            return "finish"
        
        return "retry"
    
    async def node_web_search (self, state: AdaptiveRagState):
        try:
            def ddg(query):
                with DDGS() as ddgs:
                    results = [r["body"] for r in ddgs.text(query, max_results= 5)]
                    return "\n".join(results)
                
            uuid_tmp = uuid.uuid4()
            search_result = await asyncio.to_thread(ddg, state["question"])
            search_chunk = TextChunkWithDocument(
                id=uuid_tmp,
                title="DuckDuckGo Search",
                start_page_id= uuid_tmp,
                from_page=0,
                to_page=0,
                text= search_result,
                document=uuid_tmp,
                document_object=Document(id=uuid_tmp, library="web_search", title="DuckDuckGo Search", yearIssued = 2026)
            )
            if (DEBUG_PRINT):
                print(f"Internet search result: {search_chunk}")
            return {"documents" : state["documents"] + [search_chunk], "web_search_performed" : True}
                
        except Exception as e:
            if (DEBUG_PRINT):
                print(f"Web search failed. Error: {e}")
            return {"web_search_performed" : True}


    #--- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---

    #method that is implemented in base rag class - basicly just preprocessing of request and calling generate method
    async def rag_request(self, request: RagRequest, searcher: WeaviateSearch) -> RagResponse:
        if (self.searcher == None):
            self.searcher = searcher
        
        previous_documents = []
        if request.history:
            history_preprocessed = [msg.model_dump() for msg in request.history]
            previous_documents = request.previous_documents
        else:
            history_preprocessed = []

        print(previous_documents)
        # call model
        try:
            t1 = time()

            intial_state_values = {
                "original_question" : request.question,
                "question" : request.question,
                "queries" : [],
                "context_sufficient" : False,
                "history": history_preprocessed,
                "documents": previous_documents,
                "metadata": {},
                "retrieval_iteration_counter": 0,
                "generation_iteration_counter": 0,
                "metadata_extraction_allowed": self.metadata_extraction_allowed,
                "feedback": "",
                "web_search_performed" : False
            }
            
            config = {"recursion_limit" : 25}

            generated_result = await self.rag.ainvoke(intial_state_values, config=config)

            time_spent = time() - t1

        except (openai.AuthenticationError, langchain_google_genai.chat_models.ChatGoogleGenerativeAIError) as e:
            logging.warning(e)
            raise HTTPException(status_code=401, detail="Invalid API key.")
        except Exception as e:
            logging.error(f"RAG error: calling model {self.model_type}: {e}")
            raise HTTPException(status_code=503, detail="RAG error: Service is not avalaible.")

        answer_id = str(uuid.uuid4())

        # answer
        return RagResponse(
            rag_answer=generated_result["generation"].strip(),
            sources=generated_result["documents"],
            time_spent=time_spent,
            response_id= answer_id
        )
    
    #--- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---
    # explain selection method
    async def explain_selection(self, request : ExplainRequest):
        full_answer = request.full_answer
        sources_raw = request.sources
        selected_text = request.selected_text
        history_preprocessed = []
        if request.history:
            history_preprocessed = [msg.model_dump() for msg in request.history]

        if (DEBUG_PRINT):
            print(f"EXPLAIN SELECTION: Full answer: {full_answer}, Selected text: {selected_text}")

        if (full_answer and sources_raw and selected_text):
            context = self._format_weaviate_context(sources_raw)
            chain = self._create_chain(model=self.model, prompt=self.explain_selected_text_prompt)
            result = await chain.ainvoke({
                "full_answer" : full_answer,
                "context_string" : context,
                "selected_text" : selected_text,
                "prompt_history" : history_preprocessed
            })
        return {"explanation" : result}