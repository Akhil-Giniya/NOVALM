import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from novalm.fastapi_app.schemas.chat import ChatCompletionRequest
from novalm.core.orchestrator import Orchestrator

router = APIRouter()

# Dependency override mechanism could be used here to inject orchestrator,
# but for simplicity we rely on a global app_state or singleton injection in main.py.
# However, router needs access to orchestrator.

# We will define a dependency that retrieves the orchestrator from app.state
from fastapi import Request

def get_orchestrator(request: Request) -> Orchestrator:
    return request.app.state.orchestrator

from novalm.fastapi_app.schemas.ingest import IngestRequest

@router.post("/ingest")
async def ingest_documents(
    request: IngestRequest,
    orchestrator: Orchestrator = Depends(get_orchestrator)
):
    """
    Ingests documents into the RAG memory.
    """
    orchestrator.memory.add_documents(request.documents, request.metadatas)
    return {"status": "success", "count": len(request.documents)}

@router.post("/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    orchestrator: Orchestrator = Depends(get_orchestrator)
):
    """
    OpenAI-compatible chat completions endpoint.
    Only supports streaming=True for now as per PRD requirement for SSE.
    """
    
    # Enforce streaming for now if strictly required, or handle both.
    # User said "Required SSE Format", "Responses will be streamed".
    
    async def event_generator():
        # Orchestrator yields ChatCompletionResponseChunk objects
        try:
            async for chunk in orchestrator.handle_chat(request):
                # Serialize to JSON
                data = chunk.model_dump_json()
                yield f"data: {data}\n\n"
            
            yield "data: [DONE]\n\n"
        except Exception as e:
            # logging.error(f"Error during generation: {e}")
            # In SSE, sending an error middle of stream is tricky.
            # We might send a specific error event if client supports it,
            # but standard is often just closing or sending error content.
            # For now, minimal handling.
            error_data = json.dumps({"error": str(e)})
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
