import os
import torch
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

# — your Gemma wrapper —
class EmbeddingGemma:
    def __init__(self, model_name: str = "BAAI/bge-multilingual-gemma2"):
        print(f"Loading Gemma model {model_name}…")
        self.model = SentenceTransformer(
            model_name,
            model_kwargs={"torch_dtype": torch.float16}
        )
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = self.model.to(self.device)
        self.instruction = 'Given a web search query, retrieve relevant passages that answer the query.'
        self.prompt = f'<instruct>{self.instruction}\n<query>'

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        # returns shape (len(texts), dim)
        return self.model.encode(texts, convert_to_numpy=True)

    def embed_query(self, query: str) -> np.ndarray:
        print("Embedding query", flush=True)
        emb = self.model.encode([query], prompt=self.prompt, convert_to_numpy=True)
        return emb[0]


# — FastAPI app & Pydantic schemas —
app = FastAPI(title="Gemma Embedding Worker", version="0.1.0")

class DocsRequest(BaseModel):
    texts: list[str]

class QueryRequest(BaseModel):
    query: str

# instantiate once on startup
gemma: EmbeddingGemma

@app.on_event("startup")
def load_model():
    global gemma
    model_name = os.getenv("GEMMA_MODEL", "BAAI/bge-multilingual-gemma2")
    gemma = EmbeddingGemma(model_name)

@app.post("/embed_documents")
def embed_documents(body: DocsRequest):
    if not body.texts:
        raise HTTPException(400, "No texts provided")
    embs = gemma.embed_documents(body.texts)
    # convert to native Python lists for JSON serialization
    return {"embeddings": embs.tolist()}

@app.post("/embed_query")
def embed_query(body: QueryRequest):
    if not body.query:
        raise HTTPException(400, "Empty query")
    emb = gemma.embed_query(body.query)
    return {"embedding": emb.tolist()}
