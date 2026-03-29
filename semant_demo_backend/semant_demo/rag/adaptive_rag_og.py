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
from semant_demo.rag.adaptive_rag_og_prompts import *

DEBUG_PRINT = True

#graders
#grade relevancy of retrived documents
class GraderChunkRelevance(BaseModel):
    binary_score: str = Field(description="Documents are relevant to the question, 'yes' or 'no'")

#grade relevancy of the answer
class GraderAnswerRelevance(BaseModel):
    binary_score: str = Field(description="Is an answer base on the context, 'yes' or 'no'")

@register_rag_class
class AdaptiveRagGeneratorOg(BaseRag):
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
        else:       #OPENAI / OPENROUTER
            return ChatOpenAI(
                model = model_name if model_name else self.global_config.OPENAI_MODEL,
                api_key = api_key if api_key else self.global_config.OPENAI_API_KEY,
                base_url = self.global_config.OPENAI_API_URL,
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
                "supported": END,
                "not_supported": "generate",
                "web_search" : "web_search"
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
        if (state["metadata_extraction_allowed"] == True):
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
        retry_additional_text = ""
        iteration = state.get("retrieval_iteration_counter", 0)
        
        if self.qt_strategy == "multi_query":
            if (DEBUG_PRINT):
                print(f"Multi query mode")

            if (iteration > 0):
                joint_queries = "\n".join(state["queries"])
                retry_additional_text = multiquery_retry.format(queries = joint_queries)
                if (DEBUG_PRINT):
                    print(f"Retrying multi-query feedback: {retry_additional_text}")
            
            chain = self._create_chain(model = self.model, prompt=self.multiquery_prompt)
            result_raw = await chain.ainvoke({"question_string" : state["question"] + retry_additional_text})
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

            if (iteration > 0):
                last_hyde_doc = state["queries"][0] if state["queries"] else ""
                retry_additional_text = hyde_retry.format(hyde_doc = last_hyde_doc)
                if (DEBUG_PRINT):
                    print(f"Retrying HyDe feedback: {retry_additional_text}")

            chain = self._create_chain(model = self.model, prompt=self.hyde_prompt)
            hypothetical_doc = await chain.ainvoke({"question_string" : state["question"] + retry_additional_text})

            if (DEBUG_PRINT):
                print(f"Hypothetical doc (first 100 char): {hypothetical_doc[:100]}...")

            return {"queries" : [hypothetical_doc]}
        else:
            return {"queries" : [state["question"]]}

    async def node_grade_context(self, state: AdaptiveRagState):
        chain = self._create_chain(model=self.model, prompt=self.context_grader_prompt)

        async def grader_single_doc(doc):
            clean_doc = self._get_clean_doc(doc)
            print(f"Doc to be graded: {clean_doc}")
            result_raw = await chain.ainvoke({
                "question_string" : state["question"],
                "document" : clean_doc
            })

            clean_result = re.sub(r'```json|```', '', result_raw).strip()
            try:
                graded_doc = json.loads(clean_result)
                score = graded_doc.get("binary_score", "no").lower()
                if "yes" in score:
                    return doc
            except Exception:
                return doc
            return None
            
        #call in parallel
        grade_tasks = [grader_single_doc(doc) for doc in state["documents"]]
        doc_responses = await asyncio.gather(*grade_tasks)
        #remove None
        filtered_documents = [doc for doc in doc_responses if doc is not None]

        #not relevant documents found
        if filtered_documents == []:
            return {"documents" : [],
                    "metadata_extraction_allowed": False }

        #if relevant return documents (in original textchunk format)
        if (DEBUG_PRINT):
            print(f"Relevant documents number: " + str(len(filtered_documents)), " original doc number: " + str(len(state["documents"])))
        return {"documents" : filtered_documents}
    
    def after_context_grade (self, state: AdaptiveRagState):
        #generate if there are relevant documents
        if (state["documents"]):
            return "generate"
        else:
            if (state.get("retrieval_iteration_counter", 0) < self.max_retries):
                print(f"No documents found, transformig query. Turning metadata extraction OFF.")
                return "transform"
            else:
                pass
                #Internet search will be performed if enabled
        return "generate"

    # generate an answer
    async def node_generate(self, state: AdaptiveRagState):
        #no relevant chunks found -> skip generation
        if (state["documents"] == []):
            return {"generation": "Sorry, I can't answer the question."} 

        #feedback
        feedback = state.get("feedback", "")
        feedback_prompt_add = ""
        if (feedback != "" and feedback != "supported"):
            feedback_prompt_add = generation_retry.format(feedback=feedback)


        #join snippets
        final_context = self._format_weaviate_context(state["documents"])

        if (state["history"]):
            chain = self._create_chain(model=self.model, prompt=self.main_prompt_history)
            #get history in desired format
            prompt_history = self._get_prompt_history(state["history"])

            answer = await chain.ainvoke({
                "context_string" : final_context + feedback_prompt_add,
                "original_question" : state["original_question"],
                "question_string" : state["question"],
                "prompt_history" : prompt_history
            })
        else:
            chain = self._create_chain(model=self.model, prompt=self.main_prompt)
            answer = await chain.ainvoke({
                "context_string" : final_context + feedback_prompt_add,
                "question_string" : state["question"]
            })

        if (DEBUG_PRINT):
            print(f"rag answer: {answer}")

        return {"generation": answer}
    
    async def node_grade_generation (self, state: AdaptiveRagState):
        counter_value = state.get("generation_iteration_counter", 0) + 1
        #in case self reflection is of or web search was performed there is no reason to generate feedback because it will be ignored anyway
        if (self.self_reflection == False or state["web_search_performed"] == True):
            if (DEBUG_PRINT):
                print(f"Self reflection mode is OFF")
            return {"feedback" : "supported", "generation_iteration_counter": counter_value}
        else:
            if (DEBUG_PRINT):
                print(f"Self reflection mode is ON")

            if (state["generation"].startswith("Sorry")):
                #no relevant documents/chunks found -> do not grade (try web search if enabled)
                if (self.web_search_enabled == True):
                    return {"feedback" : "", "generation_iteration_counter": counter_value}
            
            #grade answer and get feedback
            chain = self._create_chain(model=self.model, prompt=self.generation_grader_prompt)
            context = self._format_weaviate_context(state["documents"])

            raw_result = await chain.ainvoke({
                "documents" : context,
                "answer" : state["generation"]
            })

            clean_result = re.sub(r'```json|```', '', raw_result).strip()
            is_supported = True
            feedback = "supported"
            try:
                graded_answer = json.loads(clean_result)
                score = graded_answer.get("binary_score", "no").lower()
                feedback = graded_answer.get("feedback", "")
                if "no" in score:
                    is_supported = False
            except Exception:
                feedback = ""
            
            if (is_supported == True):
                if (DEBUG_PRINT):
                    print(f"Answer is supported.")
                return {"feedback" : "supported", "generation_iteration_counter": counter_value}
            else: # not supported
                if (DEBUG_PRINT):
                    print(f"Answer is not supported, feedback: {feedback}")
                return {"feedback" : feedback, "generation_iteration_counter": counter_value}

    def decide_after_generation (self, state: AdaptiveRagState):
        feedback = state.get("feedback", "")
        if (feedback == "supported"):
            return "supported"
        elif (state.get("web_search_performed") == True): #search only once
            return "supported"
        else:   #not supported
            #case where no relevant documents were found --> search web if allowed
            if (state["feedback"] == "" or state["documents"] == []):
                if self.web_search_enabled == True:
                    if (DEBUG_PRINT):
                        print(f"No relevant documents found, searching on the web.")
                    return "web_search"
                else: #return "sorry answer"
                    return "supported"
                
            #retry based on the feedback
            if (state.get("generation_iteration_counter") < self.max_retries):
                if (DEBUG_PRINT):
                    print(f"Retrying with additional feedback.")
                return "not_supported"
            
            #retried enaught times --> search web if allowed
            if (self.web_search_enabled == True and state["documents"] == []):
                if (DEBUG_PRINT):
                    print(f"Searching on the web.")
                return "web_search"
        return "supported"
    
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