from ..database import collection
from ..models.llm_models import llm
import uuid

def add_to_rag(filename: str, content: str):
    # Chunk text (simple splitting)
    chunk_size = 500
    chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]
    
    ids = [f"{filename}_{i}" for i in range(len(chunks))]
    metadatas = [{"filename": filename} for _ in chunks]
    
    # Get embeddings
    embeddings = [llm.embed(chunk) for chunk in chunks]
    
    collection.add(
        ids=ids,
        documents=chunks,
        embeddings=embeddings,
        metadatas=metadatas
    )

def query_rag(query: str, k: int = 3) -> str:
    query_emb = llm.embed(query)
    results = collection.query(query_embeddings=[query_emb], n_results=k)
    
    if results['documents'] and results['documents'][0]:
        return "\n".join(results['documents'][0])
    return ""