from pydantic import BaseModel
from typing import List, Dict, Optional

class IngestRequest(BaseModel):
    documents: List[str]
    metadatas: Optional[List[Dict[str, str]]] = None
