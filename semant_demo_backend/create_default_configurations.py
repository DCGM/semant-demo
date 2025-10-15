#!/usr/bin/env python3
from pathlib import Path

from classconfig import Config

from semant_demo.summarization.templated import TemplatedSearchResultsSummarizer

SCRIPT_PATH = Path(__file__).parent

# Create default configuration file for search results summarizer

Config(TemplatedSearchResultsSummarizer).save(str(SCRIPT_PATH / "./semant_demo/configs" / "search_summarizer.yaml"))
