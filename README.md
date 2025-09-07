# semAND - demo application

This is a demonstration application for project semANT. It indexes large number of text documents and provides:
- Search - combination of vector and full text search with metadata filters
- Search result summarization and question answering
- User document collection with text tagging 
- RAG
- ...

# Technology used
- Weaviate vector database
- FastAPI
- Vue.js
- Quasar

# Contribution guidelines
- Create an issue and a new branch with the same name
- Issue should have these parts:
  - Descriptive title
  - Short summary (2 sentences - one paragraph) inlcuding the purpose of the work.
  - Checklist of what needs to be done (technical)
  - Checklist of how to verify correct implementation - what should someone do to test the functionality
- Work on your branch
- Write notes, questions, observations, and other as issue comments
- Write basic tests
- Update relevant readme or documentation. Create/update diagrams where appropriate.
- Merge **main** into your branch and resolve conflicts
- Create a pull request and assign a reviewer
- After successfull review, merge/rebase the pull request and delete the branch

# Deploy
Deploy files are in ```/deploy```. The application would be started by ```docker compose up -d``` in the directory. Only Weaviate DB is started at the moment.

- Weaviate runs on semant.fit.vutbr.cz on localhost
  - 127.0.0.1:8089
  - 127.0.0.1:50059

