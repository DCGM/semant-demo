import asyncio
from typing import List
from semant_demo import schemas
from semant_demo.ollama_proxy import OllamaProxy
from semant_demo.config import Config

title_prompt = "Generate a title in Czech from the following text: \"{text}\" \n " \
        "The title should be relevant for this search query: \"{query}\" \n" \
        "If the the text is not relavant, write \"N/A\" \n"
summary_prompt = "Generate a sort summary in Czech from the following text: \"{text}\" \n " \
        "The summary should be in a list of concise facts extracted from the text which are relevant for this search query: \"{query}\""  

class SummaryGenerator:
    def __init__(self, config: Config):
        self.ollama_proxy = OllamaProxy(config.OLLAMA_URLS)
        self.ollama_model = config.OLLAMA_MODEL
        self.title_prompt = title_prompt
        self.summary_prompt = summary_prompt

    
    async def process_with_llm(self, req: schemas.TitleSummaryRequest) -> list[schemas.TextChunkWithDocument]:

        search_results = req.search_response.results
        query = req.search_response.search_request.query
        title_prompt_template = req.title_prompt if req.title_prompt else self.title_prompt
        summary_prompt_template = req.summary_prompt if req.summary_prompt else self.summary_prompt

        if req.title_generate:
            title_responses = [
                self.ollama_proxy.call_ollama(
                self.ollama_model,
                title_prompt_template.format(text=chunk.text, query=query)
            ) for chunk in search_results
            ]

            title_responses = await asyncio.gather(*title_responses)
            for search_result, generated_title in zip(search_results, title_responses):
                search_result.query_title = generated_title

        if req.summary_generate:
            summary_responses = [
                self.ollama_proxy.call_ollama(
                self.ollama_model,
                summary_prompt_template.format(text=chunk.text, query=query)
            ) for chunk in search_results
            ]

            summary_responses = await asyncio.gather(*summary_responses)
            for search_result, generated_summary in zip(search_results, summary_responses):
                search_result.query_summary = generated_summary

        return search_results