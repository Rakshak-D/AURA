from ..database import collection
from ..models.llm_models import llm
import uuid

def add_to_rag(filename: str, content: str):
    if collection is None:
        print("ChromaDB collection not initialized")
        return

    try:
        # Chunk text with overlap for better context
        chunk_size = 500
        overlap = 50
        chunks = []
        
        if len(content) <= chunk_size:
            chunks = [content]
        else:
            start = 0
            while start < len(content):
                end = start + chunk_size
                chunks.append(content[start:end])
                start += (chunk_size - overlap)
        
        # Generate unique IDs
        ids = [f"{filename}_{i}_{uuid.uuid4().hex[:8]}" for i in range(len(chunks))]
        metadatas = [{"filename": filename, "chunk_index": i} for i in range(len(chunks))]
        
        # Get embeddings
        embeddings = [llm.embed(chunk) for chunk in chunks]
        
        collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas
        )
        print(f"Successfully added {len(chunks)} chunks to RAG for {filename}")
        
    except Exception as e:
        print(f"Error adding to RAG: {e}")

def query_rag(query: str, k: int = 3) -> str:
    if collection is None:
        return ""
    
    try:
        query_emb = llm.embed(query)
        results = collection.query(query_embeddings=[query_emb], n_results=k)
        
        if results['documents'] and results['documents'][0]:
            return "\n".join(results['documents'][0])
        return ""
    except Exception as e:
        print(f"Error querying RAG: {e}")
        return ""