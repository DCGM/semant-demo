#!/usr/bin/env python3
from pathlib import Path

from classconfig import Config

from semant_demo.summarization.templated import TemplatedSearchResultsSummarizer
import asyncio
import logging
from semant_demo.adapters.weaviate.client import connect_weaviate
from semant_demo.adapters.weaviate.search import ChunkSearchRepository
from semant_demo.config import config
from semant_demo.features.search.filters import (
    generate_default_filters, generate_default_filters_async, save_search_filters_config,
)

SCRIPT_PATH = Path(__file__).parent

# Create default configuration file for search results summarizer

Config(TemplatedSearchResultsSummarizer).save(str(SCRIPT_PATH / "./semant_demo/configs" / "search_summarizer.yaml"))

# Create default configuration file for search filters checking DB stats (min/max year & languages)
async def default_filters():
    try:
        client = await connect_weaviate(config)
    except Exception as e:
        logging.warning(f"Could not fetch filter stats from DB: {e}")
        return generate_default_filters()
    try:
        return await generate_default_filters_async(ChunkSearchRepository(client, config.collectionNames))
    finally:
        await client.close()


filters_config = asyncio.run(default_filters())
save_search_filters_config(SCRIPT_PATH / "./semant_demo/configs" / "search_filters.yaml", filters_config)


