import os
import time
from typing import List, Dict, Tuple
from novalm.config.settings import settings

try:
    import chromadb
    from chromadb.utils import embedding_functions
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    print("WARNING: ChromaDB not found. Memory will be disabled.")

class AdvancedMemory:
    """
    Advanced Multi-Layer Memory System.
    Layers:
    1. Episodic: Past task executions (Goal -> Result).
    2. Semantic: General knowledge, docs, facts (Concept -> Info).
    3. Procedural: Heuristics and standard workflows (Trigger -> Routine).
    """
    def __init__(self):
        self.client = None
        self.episodic = None
        self.semantic = None
        self.procedural = None
        
        if CHROMA_AVAILABLE:
            # Persistent storage
            self.client = chromadb.PersistentClient(path="./data/chroma")
            self.ef = embedding_functions.DefaultEmbeddingFunction()
            
            # 1. Episodic (Formerly 'experiences')
            self.episodic = self.client.get_or_create_collection(
                name="episodic_memory",
                embedding_function=self.ef
            )
            
            # 2. Semantic (Formerly 'docs')
            self.semantic = self.client.get_or_create_collection(
                name="semantic_memory",
                embedding_function=self.ef
            )
            
            # 3. Procedural (New)
            self.procedural = self.client.get_or_create_collection(
                name="procedural_memory",
                embedding_function=self.ef
            )

    # --- EPISODIC (Past Runs) ---
    def add_episodic(self, task: str, solution: str, outcome: str, feedback: str = ""):
        if not self.episodic: return
        
        document = f"Task: {task}\nResult: {outcome}\nSolution:\n{solution}\nFeedback: {feedback}"
        meta = {"outcome": outcome, "timestamp": time.time(), "type": "episodic"}
        # Unique ID based on task hash + timestamp
        uid = f"epi_{hash(task)}_{int(time.time())}"
        
        self.episodic.add(documents=[document], metadatas=[meta], ids=[uid])
        print(f"Memory (Episodic): Saved '{task[:30]}...' ({outcome})")

    def retrieve_episodic(self, query: str, n=2) -> List[str]:
        if not self.episodic: return []
        res = self.episodic.query(query_texts=[query], n_results=n)
        return res["documents"][0] if res and res["documents"] else []

    # --- SEMANTIC (Knowledge) ---
    def add_semantic(self, content: str, source: str = "manual"):
        if not self.semantic: return
        uid = f"sem_{hash(content)}_{int(time.time())}"
        self.semantic.add(documents=[content], metadatas=[{"source": source, "timestamp": time.time()}], ids=[uid])
        print(f"Memory (Semantic): Saved content from {source}")

    def retrieve_semantic(self, query: str, n=2) -> List[str]:
        if not self.semantic: return []
        res = self.semantic.query(query_texts=[query], n_results=n)
        return res["documents"][0] if res and res["documents"] else []

    # --- PROCEDURAL (Workflows/Heuristics) ---
    def add_procedural(self, trigger: str, routine: str):
        """
        Trigger: When to use this (e.g. "Handling Deadlocks")
        Routine: The steps/workflow.
        """
        if not self.procedural: return
        document = f"Context: {trigger}\nWorkflow:\n{routine}"
        uid = f"proc_{hash(trigger)}_{int(time.time())}"
        self.procedural.add(documents=[document], metadatas=[{"trigger": trigger, "timestamp": time.time()}], ids=[uid])
        print(f"Memory (Procedural): Saved workflow for '{trigger}'")

    def retrieve_procedural(self, query: str, n=2) -> List[str]:
        if not self.procedural: return []
        res = self.procedural.query(query_texts=[query], n_results=n)
        return res["documents"][0] if res and res["documents"] else []

    # --- AGGREGATE ---
    def retrieve_all(self, query: str) -> Dict[str, List[str]]:
        return {
            "episodic": self.retrieve_episodic(query),
            "semantic": self.retrieve_semantic(query),
            "procedural": self.retrieve_procedural(query)
        }

# Alias for compatibility during refactor if needed, 
# although we should update consumers.
VectorMemory = AdvancedMemory
