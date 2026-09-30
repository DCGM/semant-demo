#!/usr/bin/env python3
from pathlib import Path

from classconfig import Config

from semant_demo.summarization.templated import TemplatedSearchResultsSummarizer
import asyncio
from semant_demo.search_filters import generate_default_filters_async, save_search_filters_config

SCRIPT_PATH = Path(__file__).parent

# Create default configuration file for search results summarizer

Config(TemplatedSearchResultsSummarizer).save(str(SCRIPT_PATH / "./semant_demo/configs" / "search_summarizer.yaml"))

# Create default configuration file for search filters checking DB stats (min/max year & languages)
filters_config = asyncio.run(generate_default_filters_async())
save_search_filters_config(SCRIPT_PATH / "./semant_demo/configs" / "search_filters.yaml", filters_config)


