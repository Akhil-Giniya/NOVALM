import os
from typing import List
from novalm.config.settings import settings

try:
    import chromadb
    from chromadb.utils import embedding_functions
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    print("WARNING: ChromaDB not found. RAG will be disabled/mocked.")

class VectorMemory:
    """
    Simple Vector Store using ChromaDB.
    """
    def __init__(self):
        self.client = None
        self.collection = None
        
        if CHROMA_AVAILABLE:
            # Persistent storage in ./data or similar ensures data survives restart
            self.client = chromadb.PersistentClient(path="./data/chroma")
            
            # Use default embedding function (Sentence Transformers usually)
            # For production, might want valid keyed providers or local HF models explicitly.
            # Default is all-MiniLM-L6-v2
            self.ef = embedding_functions.DefaultEmbeddingFunction()
            
            self.collection = self.client.get_or_create_collection(
                name="novalm_rag",
                embedding_function=self.ef
            )
            
    def add_documents(self, documents: List[str], metadatas: List[dict] = None):
        if not self.collection:
            return
            
        # IDs are required
        ids = [str(hash(doc)) for doc in documents]
        
        self.collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        
    def retrieve(self, query: str, n_results: int = 3) -> List[str]:
        if not self.collection:
            return []
            
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results
        )
        
        # results["documents"] is List[List[str]]
        if results and results["documents"]:
            return results["documents"][0]
        return []
