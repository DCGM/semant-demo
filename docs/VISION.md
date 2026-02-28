# Project Vision & Purpose

## Overview

**semANT** (_Sémantický průzkumník textového kulturního dědictví_) is a research project (NAKI III, ID DH23P03OVV060) developing tools for semantic exploration of Czech textual cultural heritage. The demonstration application **Quezio** is the primary user-facing deliverable: an interactive web platform for searching, analysing and annotating large collections of digitised historical documents.

The project consortium comprises:

- **Brno University of Technology (VUT)** — coordinator, technical development
- **Moravian Library (MZK)** — digitised document collections, domain expertise
- **Masaryk University (MUNI)** — user-experience research, bias analysis

## Goals

1. **Unified semantic search** over hundreds of thousands of digitised document pages — combining classical full-text (BM25), vector-similarity and hybrid retrieval.
2. **AI-assisted document analysis** — automatic summarisation, retrieval-augmented question answering (RAG), and topic/tag discovery.
3. **Collaborative annotation** — users can create collections, apply tags (manually or via LLM propagation), and share results.
4. **Accessible research tool** — designed for historians, literary scholars, digital humanists, librarians, and students who need to work with large corpora without deep technical skills.

## Data Pipeline

The application consumes documents produced by an upstream processing chain:

```
Kramerius digital libraries
        │
        ▼
   Download images + bibliographic metadata
        │
        ▼
   PERO OCR  →  TextBite (logical page segmentation)
        │
        ▼
   Text Chunking (cross-page blocks, ~paragraph level)
        │
        ▼
   Named Entity Recognition (persons, places, institutions, …)
        │
        ▼
   Embedding generation (BAAI/bge-multilingual-gemma2)
        │
        ▼
   Weaviate insertion (db_insert_jsonl.py)
```

Each chunk stored in Weaviate carries its text, vector embedding, NER annotations, and a reference to its parent document with full bibliographic metadata.

## Target Users (Personas)

### Media Historian / Analyst
Studies how press shaped public values. Needs to compare document sets (e.g. party newspapers vs tabloids), track topics across time, and export tagged results. Typical workflow: create a collection filtered by metadata → discover tags → propagate across corpus → visualise on timeline.

### Literary Scholar
Analyses themes, narrative structures and rhetorical patterns in fiction. Needs sentiment-like clustering, temporal visualisations, and the ability to distinguish authors/genres via metadata filtering.

### Art Historian / Curator
Researches material for exhibitions. Needs to combine full-text and semantic search, locate mentions of specific artists or movements, and collect relevant passages into user collections with notes.

### Student
Researches assignments using digitised primary sources. Needs simple natural-language queries with clear source citations.

### Digital Humanities Researcher
Uses advanced features: semantic similarity, AI-assisted tagging, RAG-based cross-document Q&A, and export of visualisations and data subsets.

## Planned Capabilities (Roadmap)

The following features are planned or in early prototype stages:

- **Agentic search & agentic RAG** — multi-step autonomous retrieval pipelines
- **Topic discovery** — unsupervised topic modelling over collections
- **Zero-shot / few-shot tagging** — tag propagation with minimal user examples (Topicer module)
- **Similarity navigation** — select text → find similar passages, optionally constrained by topic
- **Advanced visualisations** — word clouds, temporal distributions, co-occurrence graphs
- **Discussion / annotation sharing** — collaborative comments on text passages
- **Export** — tagged data, visualisations, permanent links to query results

## Related Project Outputs

| Output | Description |
|---|---|
| **Topicer** | Software for unsupervised topic discovery and zero/few/many-shot topic tagging |
| **TextBite** | Logical page segmentation for historical Czech documents |
| **TextJuicer** | Summarisation model evaluation and distillation |
| **BenCzechMark** | Czech LLM benchmark |
| Embedding study | _"A Comparative Study of Text Retrieval Models on DaReCzech"_ |

## Design Inspirations

The UI and feature set draws from:

- **Newton Media** — topic/tag sidebar, entity filtering (must/may/must-not)
- **Kramerius / Polona** — faceted search, temporal filters, author/keyword autocomplete
- **WebLyzard** — association clouds, trend charts with events, geographic maps
- **WolframAlpha** — structured data display and export
- **Voyant Tools** — word frequency trends, dispersion plots
- **Atlas.ti / CATMA / Taguette** — qualitative coding tools for document annotation
