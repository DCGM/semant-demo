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

import logging
import re
import json
import asyncio

from semant_demo.rag.rag_factory import BaseRag, register_rag_class
from semant_demo.config import Config
from semant_demo.schemas import SearchResponse, SearchRequest, RagRequest, RagResponse, AdaptiveRagState, TextChunkWithDocument, Document, ExplainRequest
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction
#import prompts from prompt file
from semant_demo.rag.incremental_rag_prompts import *

DEBUG_PRINT = True

@register_rag_class
class IncrementalAdaptiveRagGenerator(BaseRag):
    def __init__(self, global_config: Config, param_config):
        super().__init__(global_config, param_config)
        self.searcher = None

        #multilanguage prompt
        self.identify_language_prompt = ChatPromptTemplate.from_messages(identify_language_prompt_template)
        self.identify_language_prompt_answer = ChatPromptTemplate.from_messages(identify_language_answer_prompt_template)
        self.check_sufficient_context_prompt = ChatPromptTemplate.from_messages(check_sufficient_context_prompt_template)
        
        self.prompts = {
            "ces" : {
                "history_transformation" : ChatPromptTemplate.from_messages(cze_refrase_question_from_history_prompt_template),
                "generate_no_history" : ChatPromptTemplate.from_messages(cze_answer_question_prompt_template),
                "generate_with_history" : ChatPromptTemplate.from_messages(cze_answer_question_with_history_prompt_template),
                "multiquery" : ChatPromptTemplate.from_messages(cze_multiquery_prompt_template),
                "grade_context" : ChatPromptTemplate.from_messages(cze_context_grader_prompt_template),
                "grade_generation" : ChatPromptTemplate.from_messages(cze_generation_grader_prompt_template),
                "extract_keyword" : ChatPromptTemplate.from_messages(cze_extract_keyword_prompt),
                "extract_metadata" : ChatPromptTemplate.from_messages(cze_extract_metadata_from_question_template),
                "hyde" : ChatPromptTemplate.from_messages(cze_hyde_prompt_template),
                "consider_web" : ChatPromptTemplate.from_messages(cze_consider_web_search_prompt),
                "explain_selected_text" : ChatPromptTemplate.from_messages(cze_explain_selected_text_prompt_template)

            },
            "eng" : {
                "history_transformation" : ChatPromptTemplate.from_messages(eng_refrase_question_from_history_prompt_template),
                "generate_no_history" : ChatPromptTemplate.from_messages(eng_answer_question_prompt_template),
                "generate_with_history" : ChatPromptTemplate.from_messages(eng_answer_question_with_history_prompt_template),
                "multiquery" : ChatPromptTemplate.from_messages(eng_multiquery_prompt_template),
                "grade_context" : ChatPromptTemplate.from_messages(eng_context_grader_prompt_template), 
                "grade_generation" : ChatPromptTemplate.from_messages(eng_generation_grader_prompt_template),
                "extract_keyword" : ChatPromptTemplate.from_messages(eng_extract_keyword_prompt),
                "explain_selected_text" : ChatPromptTemplate.from_messages(eng_explain_selected_text_prompt_template),
                "extract_metadata" : ChatPromptTemplate.from_messages(eng_extract_metadata_from_question_template),
                "hyde" : ChatPromptTemplate.from_messages(eng_hyde_prompt_template)
            }
        }

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
        self.max_retries = param_config.get("max_retries", 3)
        self.web_search_enabled = param_config.get("web_search_enabled", False)
        self.metadata_extraction_allowed = param_config.get("metadata_extraction_allowed", True)
        #build
        self.workflow = self._build_rag()
        self.rag = self.workflow.compile()

        if (DEBUG_PRINT == True):
            print("Adaptive RAG version 25_4_3")

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
                temperature = 0.0,
                num_ctx = 16384
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
    
    def _get_prompt_by_language(self, node_type: str, language: str):
        lang_dict = self.prompts.get(language, self.prompts.get("ces"))
        return lang_dict.get(node_type, self.prompts["ces"].get(node_type))


     # create the graph
    def _build_rag(self):
        #define nodes
        workflow = StateGraph(AdaptiveRagState)
        workflow.add_node("detect_language", self.node_detect_language)
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
        workflow.add_edge(START, "detect_language")

        workflow.add_edge("detect_language", "transform_history")
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
                "web_search" : "web_search",
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
        try:
            #get metadata
            metadata = state.get("metadata", {})
            iteration = state.get("retrieval_iteration_counter", 0)

            limit = self.chunk_limit
            alpha = self.alpha
            use_hyde_embedding = False
            if (iteration == 0):
                limit = 5
            elif (iteration == 1):
                limit = self.chunk_limit
            elif (iteration == 2):  # hyde
                #use document embedding instead of query embedding
                limit = 10
                use_hyde_embedding = True
                alpha = 0.9

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
                    hybrid_search_alpha = alpha,
                    limit = limit,
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
                return await self.searcher.textChunk.search(search_request)

            #call in parallel
            search_tasks = [single_search(query) for query in queries]
            search_responses = await asyncio.gather(*search_tasks)
            
            #remove duplicities and put it together
            unique_chunks = {}
            for response in search_responses:
                # for chunk in response.results[:3]:
                for chunk in response.results:
                    chunk_id = getattr(chunk, "id", None)
                    if chunk_id not in unique_chunks:
                        unique_chunks[chunk_id] = chunk

            all_chunks = list(unique_chunks.values())
            all_chunks = all_chunks[:10]

            counter_value = state.get("retrieval_iteration_counter", 0) + 1

            return  {"documents" : all_chunks, 
                    "retrieval_iteration_counter" : counter_value
                    }
        except Exception as e:
            logging.error(f"RAG ERROR: retrieval: {str(e)}")
            counter_value = state.get("retrieval_iteration_counter", 0) + 1
            return  {"documents" : [], 
                    "retrieval_iteration_counter" : counter_value
                    }
    
    async def node_detect_language(self, state: AdaptiveRagState):
        chain = self._create_chain(model=self.model, prompt=self.identify_language_prompt)
        result = await chain.ainvoke({"question_string" : state["question"]})
        clean_result = re.sub(r'```json|```', '', result).strip()
        try:
            graded_doc = json.loads(clean_result)
            language = graded_doc.get("language", "eng").lower()
            if (DEBUG_PRINT):
                print(f"Detected language: {language}")
        except Exception:
            return {"language" : "eng"}
        return {"language" : language}


    #rephrase question to search desired data in database
    async def node_history_transformation(self, state: AdaptiveRagState):
        if (state["history"]):
            #create desired chain
            prompt = self._get_prompt_by_language("history_transformation", state["language"])
            chain = self._create_chain(model=self.model, prompt=prompt)

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
        if state.get("retrieval_iteration_counter", 0) == 1:
            if (state["metadata_extraction_allowed"] == True):
                if (DEBUG_PRINT): 
                    print("Extrackting metadata in Multi-query iteration")
                language = state.get("language", "ces")
                prompt = self._get_prompt_by_language("extract_metadata", language)
                chain =  self._create_chain (model=self.extract_model, prompt=prompt)
                result = await chain.ainvoke({"question_string" : state["question"]})
                clean_result = re.sub(r'```json|```', '', result).strip()
                try:
                    metadata = json.loads(clean_result)
                    metadata_structured = {
                        "min_year" : (int(metadata.get("min_year")) - 5) if metadata.get("min_year") else None,
                        "max_year" : (int(metadata.get("max_year")) + 5) if metadata.get("max_year") else None,
                        "language" : metadata.get("language")
                    }
                    if (DEBUG_PRINT):
                        print(f"metadata_structured: {metadata_structured}")
                    return {"metadata" : metadata_structured}
                except Exception:
                    return {"metadata" : {}}
        if state.get("metadata", {}) != {}:
            return {"metadata" : state["metadata"]}

        return {"metadata" : {}}
        
    async def node_multi_query(self, state: AdaptiveRagState):
        iteration = state.get("retrieval_iteration_counter", 0)
        language = state.get("language", "ces")
        #first time try simple retrieve
        if (iteration == 0):
            return {"queries" : [state["question"]]}
        
        elif (iteration == 2): # hyde
            if (DEBUG_PRINT):
                print(f"HYDE MODE")

            prompt = self._get_prompt_by_language("hyde", language)
            chain = self._create_chain(model = self.model, prompt = prompt)
            hyde = await chain.ainvoke({"question_string" : state["question"]})

            return {"queries" : [hyde]}

        else:
            #multiple query generation
            if (DEBUG_PRINT):
                print(f"MULTI QUERY MODE")

            prompt = self._get_prompt_by_language("multiquery", language)
            chain = self._create_chain(model = self.model, prompt = prompt)
            result_raw = await chain.ainvoke({"question_string" : state["question"]})

            # simple parser
            queries = [line.strip().lstrip("0123456789.- ") for line in result_raw.split("\n") if len(line.strip()) > 5]
            queries = queries[:3]

            if state["question"] not in queries:
                    queries.append(state["question"])

            return {"queries" : queries}



    async def node_grade_context(self, state: AdaptiveRagState):
        #first basic rag query
        if (len(state["documents"]) <= 5 or state["retrieval_iteration_counter"] == 1):
            return {"documents": state["documents"]}
        
        if (DEBUG_PRINT): 
            print(f"GRADING RETRIEVED CONTEXT: ({len(state['documents'])} docs)")

        language = state.get("language", "ces")
        prompt = self._get_prompt_by_language("grade_context", language)
        chain = self._create_chain(model=self.model, prompt=prompt)

        async def grader_single_doc(doc):
            clean_doc = self._get_clean_doc(doc)
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
        

        #if relevant return documents (in original textchunk format)
        if (DEBUG_PRINT):
            print(f"Relevant documents number: " + str(len(filtered_documents)), " original doc number: " + str(len(state["documents"])))
        
        filtered_documents = filtered_documents[:5]
        return {"documents" : filtered_documents}
    
    def after_context_grade (self, state: AdaptiveRagState):
        ret_count = state.get("retrieval_iteration_counter", 0)
        if (state["documents"] and len(state["documents"]) > 0):
            return "generate"
        
        if (DEBUG_PRINT): 
            print(f"ROUTER: 0 relevant documents in iteration {ret_count}")

        if ret_count < self.max_retries: 
            return "transform"
        
        if self.web_search_enabled and not state.get("web_search_performed"):
            return "web_search"

        return "generate"

    # generate an answer
    async def node_generate(self, state: AdaptiveRagState):
        language = state.get("language", "ces")
        
        #join snippets
        final_context = self._format_weaviate_context(state["documents"])
        if (DEBUG_PRINT):
            print(f"DEBUG: Context length (chars): {len(final_context)}")

        if (state["history"]):
            prompt = self._get_prompt_by_language("generate_with_history", language)
            chain = self._create_chain(model=self.model, prompt=prompt)
            #get history in desired format
            prompt_history = self._get_prompt_history(state["history"])

            answer = await chain.ainvoke({
                "context_string" : final_context,
                "original_question" : state["original_question"],
                "question_string" : state["question"],
                "prompt_history" : prompt_history
            })
        else:
            prompt = self._get_prompt_by_language("generate_no_history", language)
            chain = self._create_chain(model=self.model, prompt=prompt)
            answer = await chain.ainvoke({
                "context_string" : final_context,
                "question_string" : state["question"]
            })

        if (DEBUG_PRINT):
            print(f"rag answer: {answer}")

        return {"generation": answer}
    
    async def node_grade_generation (self, state: AdaptiveRagState):
        gen_value = state.get("generation_iteration_counter", 0) + 1
        language = state.get("language", "ces")
        prompt = self._get_prompt_by_language("grade_generation", language)
        chain = self._create_chain(model=self.model, prompt=prompt)

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
        retrieval_count = state.get("retrieval_iteration_counter", 0)
        web_search_done = state.get("web_search_performed", False)
        if state["feedback"] == "supported":
            if (DEBUG_PRINT): 
                print("FINISHING: Answer satisfactory.")
            return "finish"
        if (retrieval_count < self.max_retries):
            if (DEBUG_PRINT): 
                print("Retrying with multiquery or hyde.")
            return "retry"
        if (web_search_done == False and self.web_search_enabled == True):
            return "web_search"
        
        return "finish"
    
    async def node_web_search (self, state: AdaptiveRagState):
        if (DEBUG_PRINT):
            print(f"Extracting keyword for the internet search.")

        try:
            language = state.get("language", "ces")
            prompt = self._get_prompt_by_language("extract_keyword", language)
            chain = self._create_chain(model=self.model, prompt=prompt)

            keywords_raw = await chain.ainvoke({"question": state["question"]})
            keywords = keywords_raw.replace(",", " ").strip()

            search_queries = [keywords, state["question"]]
        except Exception as e:
            print(f"Rewriting web search queries, Error: {e}")

        if (DEBUG_PRINT):
            print(f"Trying to search web using DuckDuckGo")

        try:
            def ddg(queries):
                all_results = []
                with DDGS() as ddgs:
                    for q in queries:
                        if (DEBUG_PRINT): 
                            print(f"Searching web: {q}")
                        results = [r["body"] for r in ddgs.text(q, max_results = 8)]
                        all_results.extend(list(set(results)))

                unique_results = list(dict.fromkeys(all_results))
                return "\n".join(unique_results)
  
            uuid_tmp = uuid.uuid4()
            search_result = await asyncio.to_thread(ddg, search_queries)

            search_chunk = TextChunkWithDocument(
                id=uuid_tmp,
                title="DuckDuckGo Search",
                start_page_id= uuid_tmp,
                from_page=0,
                to_page=0,
                order=0,
                text= search_result,
                document=uuid_tmp,
                document_object=Document(id=uuid_tmp, library="web_search", title="DuckDuckGo Search", yearIssued = 2026)
            )
            if (DEBUG_PRINT):
                print(f"Internet search result: {search_chunk}")
            return {"documents" : [search_chunk], "web_search_performed" : True, "feedback" : "supported"}
                
        except Exception as e:
            if (DEBUG_PRINT):
                print(f"Web search failed. Error: {e}")
            return {"web_search_performed" : True, "feedback" : "supported"}


    #--- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---

    #method that is implemented in base rag class - basicly just preprocessing of request and calling generate method
    async def rag_request(self, request: RagRequest, searcher: WeaviateAbstraction) -> RagResponse:
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
            
            config = {"recursion_limit" : 50}

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
            
            # detect language
            language = "eng"
            chain = self._create_chain(model=self.model, prompt=self.identify_language_prompt_answer)
            result = await chain.ainvoke({"text_string" : full_answer})
            clean_result = re.sub(r'```json|```', '', result).strip()
            try:
                graded_doc = json.loads(clean_result)
                language = graded_doc.get("language", "eng").lower()
                if (DEBUG_PRINT):
                    print(f"Detected language: {language}")
            except Exception:
                language = "eng"

            # explain selection
            prompt = self._get_prompt_by_language("explain_selected_text", language)

            chain = self._create_chain(model=self.model, prompt=prompt)
            result = await chain.ainvoke({
                "full_answer" : full_answer,
                "context_string" : context,
                "selected_text" : selected_text,
                "prompt_history" : history_preprocessed
            })
        return {"explanation" : result}