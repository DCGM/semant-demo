Both evaluate.py and generateTests.py require .env file.
#### evaluate.py requires:
- backend url
    - BACKEND_API_URL
- desired chunk limit that will be search while searching for context
    - CHUNK_LIMIT
- models and API
    - OLLAMA_URL
    - OLLAMA_EVAL_MODEL
    - OPENAI_EVAL_MODEL
    - OPENAI_API_KEY
- default paths:
    - PATH_SYN
    - PATH_GT
    - PATH_WITHOUT_GT

#### generateTests.py requires:
- OPENAI_API_KEY