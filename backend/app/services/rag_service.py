from ..database import collection
from ..models.llm_models import llm
from ..config import config
import uuid


def add_to_rag(filename: str, content: str):
    """
    Chunk a document, embed chunks, and add them to the Chroma collection.
    Uses configuration values for chunking to avoid magic numbers.
    """
    if collection is None:
        print("ChromaDB collection not initialized")
        return

    try:
        # Chunk text with overlap for better context
        chunk_size = getattr(config, "RAG_CHUNK_SIZE", 500)
        overlap = getattr(config, "RAG_CHUNK_OVERLAP", 50)
        chunks = []

        if len(content) <= chunk_size:
            chunks = [content]
        else:
            start = 0
            while start < len(content):
                end = start + chunk_size
                chunks.append(content[start:end])
                start += max(chunk_size - overlap, 1)

        # Generate unique IDs
        ids = [f"{filename}_{i}_{uuid.uuid4().hex[:8]}" for i in range(len(chunks))]
        metadatas = [{"filename": filename, "chunk_index": i} for i in range(len(chunks))]

        # Get embeddings
        embeddings = [llm.embed(chunk) for chunk in chunks]

        collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        print(f"Successfully added {len(chunks)} chunks to RAG for {filename}")

    except Exception as e:
        print(f"Error adding to RAG: {e}")


def delete_document_embeddings(filename: str) -> int:
    """
    Remove all embeddings from the Chroma collection that belong to a document.

    We delete by metadata.filename which we set when adding chunks.

    Returns the number of deleted items if available, otherwise 0.
    """
    if collection is None:
        print("ChromaDB collection not initialized")
        return 0

    try:
        # Some Chroma backends may not return a count; in that case just perform delete.
        result = collection.delete(where={"filename": filename})
        # result can be None or a dict depending on backend version
        if isinstance(result, dict):
            return int(result.get("count", 0))
        return 0
    except Exception as e:
        print(f"Error deleting embeddings for {filename}: {e}")
        return 0


def query_rag(query: str, k: int = None) -> str:
    if collection is None:
        return ""

    try:
        top_k = k if k is not None else getattr(config, "RAG_TOP_K", 3)
        query_emb = llm.embed(query)
        results = collection.query(query_embeddings=[query_emb], n_results=top_k)

        if results.get("documents") and results["documents"][0]:
            return "\n".join(results["documents"][0])
        return ""
    except Exception as e:
        print(f"Error querying RAG: {e}")
        return ""