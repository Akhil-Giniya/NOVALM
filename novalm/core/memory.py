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

class LongTermMemory:
    """
    Manages Long-Term Episodic Memory (Experiences) and RAG Documents.
    """
    def __init__(self):
        self.client = None
        self.doc_collection = None
        self.exp_collection = None
        
        if CHROMA_AVAILABLE:
            # Persistent storage
            self.client = chromadb.PersistentClient(path="./data/chroma")
            self.ef = embedding_functions.DefaultEmbeddingFunction()
            
            # Collection for RAG Documents
            self.doc_collection = self.client.get_or_create_collection(
                name="novalm_rag",
                embedding_function=self.ef
            )
            
            # Collection for Experiences (Task -> Solution)
            self.exp_collection = self.client.get_or_create_collection(
                name="novalm_experiences",
                embedding_function=self.ef
            )

    def add_documents(self, documents: List[str], metadatas: List[dict] = None):
        """Adds RAG documents."""
        if not self.doc_collection: return
        ids = [str(hash(doc)) for doc in documents]
        self.doc_collection.add(documents=documents, metadatas=metadatas, ids=ids)

    def retrieve_documents(self, query: str, n_results: int = 3) -> List[str]:
        """Retrieves RAG documents."""
        if not self.doc_collection: return []
        results = self.doc_collection.query(query_texts=[query], n_results=n_results)
        if results and results["documents"]:
            return results["documents"][0]
        return []

    def add_experience(self, task: str, solution: str, outcome: str, feedback: str = ""):
        """
        Stores an experience (Task, Code/Solution, Outcome, Feedback).
        Outcome: 'SUCCESS' or 'FAILURE'
        """
        if not self.exp_collection: return
        
        # Format the memory document
        # We index the TASK so we can find it again when faced with similar tasks.
        # But we verify if we should also store the solution in the text to search?
        # Usually we search by Task Query.
        
        document = f"Task: {task}\nResult: {outcome}\nSolution:\n{solution}\nFeedback: {feedback}"
        
        # Meta for filtering if needed
        meta = {"outcome": outcome, "timestamp": str(os.path.getmtime(settings.MODEL_PATH) if os.path.exists(settings.MODEL_PATH) else 0)} 
        # timestamp is just a placeholder, ideally use time.time() but avoiding new imports if possible. 
        # Actually I can import time or datetime.
        import time
        meta["timestamp"] = time.time()
        
        # ID
        experience_id = f"exp_{hash(document)}_{int(time.time())}"
        
        self.exp_collection.add(
            documents=[document],
            metadatas=[meta],
            ids=[experience_id]
        )
        print(f"Memory: Saved experience ({outcome})")

    def retrieve_experiences(self, task: str, n_results: int = 2) -> List[str]:
        """
        Retrieves relevant past experiences for a task.
        """
        if not self.exp_collection: return []
        
        results = self.exp_collection.query(
            query_texts=[task],
            n_results=n_results
        )
        
        if results and results["documents"]:
            return results["documents"][0]
        return []

# Backward compatibility alias if needed, but we will update Orchestrator
VectorMemory = LongTermMemory
