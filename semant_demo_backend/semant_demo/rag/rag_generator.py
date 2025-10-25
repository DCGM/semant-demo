from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from langchain_community.llms import Ollama


from typing import Optional, List

from semant_demo.config import Config
from semant_demo.schemas import SearchResponse, SearchRequest, SearchType
from semant_demo.weaviate_search import WeaviateSearch

# prompt
prompt_template = [
    ("system",
    """You are a precise and helpful chatbot. Your main task is to answer the user's question based STRICTLY on the provided context.
    Follow these rules exactly:
    1) Use ONLY the following pieces of context to answer the question.
    2) For every piece of information or sentence that you take out of context, you must provide source in format `[doc X]`, where X is the number of the corresponding source.\n "
    3) If multiple sources support one sentence, cite them all, like this: `[doc 2], [doc 5]`.
    4) Don't make up any new information. If you can not provide answer based on the context, answer only \"I can´t answer the question.\".
    5) Format your answer using Markdown for clarity (e.g., bullet points for lists, bold for key terms).
    Context: {context_string}\n"""),
    MessagesPlaceholder(variable_name="prompt_history"),
    ("user", "{question_string}")
    ]

class RagGenerator:
    def __init__(self, config: Config, search: WeaviateSearch):
        self.config = config
        self.prompt = ChatPromptTemplate.from_messages(prompt_template)
        self.output_parser = StrOutputParser()
        self.search = search

    # create chain of operations
    def create_chain(self, model_name: str):
        # select model
        if (model_name == "GOOGLE"):
            model = ChatGoogleGenerativeAI(
                model = self.config.GOOGLE_MODEL,
                google_api_key = self.config.GOOGLE_API_KEY,
                temperature = self.config.MODEL_TEMPERATURE
            )
        elif (model_name == "OLLAMA"):
            model = Ollama(
                model=self.config.OLLAMA_MODEL,
                base_url=self.config.OLLAMA_URLS[0],
                temperature=self.config.MODEL_TEMPERATURE
            )
        else:
            model = ChatOpenAI(
                model=self.config.OPENAI_MODEL,
                api_key=self.config.OPENAI_API_KEY,
                temperature=self.config.MODEL_TEMPERATURE
            )

        # creation of the chain
        return self.prompt | model | self.output_parser
    
    # function to get history prompt in desire format
    def get_prompt_history(self, history: list):
        prompt_history = []
        for msg in history:
            if msg['role'] == 'user':
                prompt_history.append(HumanMessage(content=msg['content']))
            elif msg['role'] == 'assistant':
                prompt_history.append(AIMessage(content=msg['content']))
        return prompt_history
    
    #function that converts incomming search results to desired format
    def format_context(self, results: List[SearchResponse]) -> str:
        snippets = [
            f"[doc{i+1}]" + res.text.replace('\\n', ' ')
            for i, res in enumerate(results)
        ]
        return ("\n".join(snippets))
    
    # execute chain
    async def generate_answer(self, model_name: str, question_string: str, history: list, context_string: Optional[str] = None, search_type: str = "hybrid", alpha: float = 0.5, limit: int = 10, search_query: Optional[str] = None ):
        final_context = context_string
        # check if context was entered
        if (final_context == None):
            #convert search type
            try:
                type = SearchType(search_type)
            except ValueError:
                raise ValueError(f"Rag error: Unknown search type: {search_type}")
            #create db search request
            search_request = SearchRequest(
                query = search_query,
                type = type,
                hybrid_search_alpha = alpha,
                limit = limit
            )
            #call db search
            search_response = await self.search.search(search_request)
            search_results = search_response.results
            #convert context to desired format
            final_context = self.format_context(search_results)
        
        chain = self.create_chain(model_name=model_name)
        prompt_history = self.get_prompt_history(history)

        result = await chain.ainvoke({
            "context_string" : final_context,
            "question_string" : question_string,
            "prompt_history" : prompt_history
        })
        return {
            "answer": result,
            "sources": search_results
        }