from ..database import collection
from ..models.llm_models import llm
from ..utils.parser import parse_document

def add_to_rag(filename: str, content: str):
    embedding = llm.embed(content)
    # Ensure ID is unique; simplistic approach using filename
    collection.add(
        embeddings=[embedding],
        documents=[content],
        metadatas=[{"filename": filename}],
        ids=[filename] 
    )

def query_rag(query: str, k: int = 3) -> str:
    query_emb = llm.embed(query)
    results = collection.query(query_embeddings=[query_emb], n_results=k)
    context = "\n".join(results['documents'][0]) if results['documents'] and results['documents'][0] else ""
    return context

def rag_qa(query: str) -> str:
    context = query_rag(query)
    if not context: return "No relevant documents found."
    prompt = f"Context: {context}\n\nQuestion: {query}\nAnswer:"
    return llm.generate(prompt)