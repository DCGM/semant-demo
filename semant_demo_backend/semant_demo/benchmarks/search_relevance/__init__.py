"""Search relevance benchmark (#712, docs/SEARCH_BENCHMARK.md).

Separate stages that exchange only versioned files (``contracts``):

* #726 generator: samples a corpus, writes intents and their queries in several languages,
  pools candidates in a benchmark store and grades them once (``qrels``);
* #730: dataset v1, produced with the generator and frozen;
* #727 runner: searches a frozen dataset in a benchmark-owned Weaviate (``store_api``) with
  configurable models and search settings, and saves the ranked results;
* #728 reports (``report``, with ``metrics``, ``analysis`` and ``plots``): metrics, tables and
  plots from saved runs, without Weaviate or a model.

Shared here: ``contracts`` (the files), ``store_api`` (the benchmark store's interface),
``llm`` (model calls through ``LlmGateway``) and ``languages``. Nothing here imports another
stage or a maintenance tool.
"""
