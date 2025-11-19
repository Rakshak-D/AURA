from database import collection
from models.llm_models import llm
from utils.parser import parse_document

def add_to_rag(filename: str, content: str):
    embedding = llm.embed(content)
    id = collection.add(
        embeddings=[embedding],
        documents=[content],
        metadatas=[{"filename": filename}],
        ids=[filename]
    )
    return id

def query_rag(query: str, k: int = 3) -> str:
    query_emb = llm.embed(query)
    results = collection.query(query_embeddings=[query_emb], n_results=k)
    context = "\n".join(results['documents'][0]) if results['documents'] else ""
    return context

def rag_qa(query: str) -> str:
    context = query_rag(query)
    prompt = f"Context: {context}\n\nQuestion: {query}\nAnswer:"
    return llm.generate(prompt)