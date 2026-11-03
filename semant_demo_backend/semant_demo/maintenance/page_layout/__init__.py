"""PERO PAGE XML -> compact per-page layout JSON and chunk-start anchors (#540).

Offline only: the running application never parses PAGE XML; it serves the files written
here (#541). The modules are pure functions, the CLI is ``__main__``:

``parse``      PAGE XML 2019-07-15 -> regions and lines in pero-ocr's order
``serialize``  the legacy chunking of ``db_benchmarks/semant/*prepare_documents.py``, with
               a trace of each chunk's line contributions
``anchors``    matching chunk texts to the serialized text: ``layoutStart`` per chunk, and
               ``replay``, the walk the frontend does from an anchor
``geometry``   integer baselines, heights and approximate word starts
``page_json``  the versioned page file
``convert``    one document end to end

The format and the rules are documented in ``docs/PAGE_LAYOUT.md``.
"""
