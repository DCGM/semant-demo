import openai
import langchain_google_genai 
from fastapi import HTTPException
from time import time

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from langchain_ollama import OllamaLLM

import logging

from semant_demo.rag.rag_factory import BaseRag, register_rag_class
from semant_demo.config import Config
from semant_demo.schemas import SearchResponse, SearchRequest, SearchType, RagSearch, RagRouteConfig, RagRequest, RagResponse
from semant_demo.weaviate_search import WeaviateSearch

# prompt
answer_question_prompt_template = [
    ("system",
    """
    You are a precise and helpful chatbot. Your main task is to answer the user's \
    question based STRICTLY on the provided context.
    Follow these rules exactly:
    1) Use ONLY the following pieces of context to answer the question.
    2) For every piece of information or sentence that you take out of context, \
    you must provide source in format `[doc X]`, where X is the number of the corresponding source."
    3) If multiple sources support one sentence, cite them all, like this: `[doc 2], [doc 5]`.
    4) Don't make up any new information. If you can not provide answer based on the context, answer only \"Sorry, I can´t answer the question.\".
    5) Format your answer using Markdown for clarity (e.g., bullet points for lists, bold for key terms).
    Context: {context_string}\n
    """),
    MessagesPlaceholder(variable_name="prompt_history"),
    ("user", "{question_string}")
    ]

refrase_question_from_history_prompt_template = [
    ("system",
    """
    Given a chat history and the latest user question \
    which might reference context in the chat history, formulate a standalone question which can be understood \
    without the chat history. Do NOT answer the question, Your goal is to make the question more specific by incorporating \
    relevant keywords and entities (like names, locations, or dates) from the chat history. \
    just reformulate it if needed and otherwise return it as is. 
    """),
    MessagesPlaceholder(variable_name="prompt_history"),
    ("user", "{question_string}")
    ]

@register_rag_class
class RagGenerator(BaseRag):
    def __init__(self, global_config: Config, param_config):
        super().__init__(global_config, param_config)
        self.searcher = None
        #this can be part of config in future
        self.main_prompt = ChatPromptTemplate.from_messages(answer_question_prompt_template)
        self.history_prompt = ChatPromptTemplate.from_messages(refrase_question_from_history_prompt_template)
        self.output_parser = StrOutputParser()
        #create model instance
        model_type = param_config.get("model_type")
        self.model_type = model_type
        api_key = param_config.get("api_key", None)
        model_name = param_config.get("model_name", None)
        temperature = param_config.get("temperature", None)
        self.model = self._create_model(model_type, model_name, api_key, temperature)
        #search parameters
        self.chunk_limit = param_config.get("chunk_limit", 5)
        self.alpha = param_config.get("alpha", 0.5)
        self.search_type = param_config.get("search_type", "hybrid")

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

    # creation of the chain - will be complex in future
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
    
    async def _call_weaviate_search(self, rag_search: RagSearch,  type: SearchType) -> SearchResponse:
        #create db search request
        search_request = SearchRequest(
            query = rag_search.search_query,
            type = self.search_type,
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
        #TODO DEBUG
        print(f"search_request: {search_request}")
        #call db search
        search_response = await self.searcher.search(search_request)
        return search_response
    
    #rephrase question to search desired data in database
    async def _rephrase_question(self, question_string: str, model, prompt_history):
        chain = self._create_chain(model=model, prompt=self.history_prompt)

        correct_question = await chain.ainvoke({
            "question_string" : question_string,
            "prompt_history" : prompt_history
        })

        #TODO DEBUG
        print(f"Refrased question: {correct_question}")

        return correct_question

    # execute chain
    async def generate_answer(self, question_string: str, history: list, rag_search: RagSearch, context_string: str | None = None):
        #create llm instance
        model = self.model

        #convert history into desired format
        prompt_history = self._get_prompt_history(history)
        #rephrase question if history is there
        question = question_string
        if (history):
            question = await self._rephrase_question(question_string=question_string, model=model, prompt_history=prompt_history)
        rag_search.search_query = question


        final_context = context_string
        # check if context was entered
        if (final_context == None):
            #convert search type
            try:
                type = SearchType(rag_search.search_type)
            except ValueError:
                raise ValueError(f"Rag error: Unknown search type: {rag_search.search_type}")
            #search in db
            search_response = await self._call_weaviate_search(type = type, rag_search = rag_search)
            search_results = search_response.results
            #convert context to desired format
            final_context = self._format_weaviate_context(search_results)
        
        chain = self._create_chain(model=model, prompt=self.main_prompt)

        #TODO DEBUG
        print(f"rag_config: {self.param_config}, rag_search: {rag_search} ")

        result = await chain.ainvoke({
            "context_string" : final_context,
            "question_string" : question_string,
            "prompt_history" : prompt_history
        })
        return {
            "answer": result,
            "sources": search_results
        }
    
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

            generated_result = await self.generate_answer(
                question_string = request.question,
                history= history_preprocessed,
                #search parameters
                rag_search = request.rag_search
            )
            time_spent = time() - t1

        except (openai.AuthenticationError, langchain_google_genai.chat_models.ChatGoogleGenerativeAIError) as e:
            logging.warning(e)
            raise HTTPException(status_code=401, detail="Invalid API key.")
        except Exception as e:
            logging.error(f"RAG error: calling model {self.model_type}: {e}")
            raise HTTPException(status_code=503, detail="RAG error: Service is not avalaible.")

        # answer
        return RagResponse(
            rag_answer=generated_result["answer"].strip(),
            sources=generated_result["sources"],
            time_spent=time_spent
        )