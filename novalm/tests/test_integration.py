from fastapi.testclient import TestClient
from novalm.fastapi_app.main import app
from novalm.config.settings import settings
from novalm.engine.vllm_engine import get_inference_engine, MockInferenceEngine
import pytest
import os

# Override settings for testing
os.environ["API_KEY"] = "test-key"
os.environ["MODEL_PATH"] = "dummy/path"
# Enable mock inference purely for API flow testing so we don't crash on CUDA
os.environ["ALLOW_MOCK_INFERENCE"] = "True"
settings.ALLOW_MOCK_INFERENCE = True


def test_auth_missing():
    with TestClient(app) as client:
        response = client.post("/v1/chat/completions", json={})
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid or missing API Key"

def test_auth_invalid():
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions", 
            json={}, 
            headers={"X-API-Key": "wrong-key"}
        )
        assert response.status_code == 401

def test_health_check():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

def test_chat_stream_flow():
    # This verifies the whole pipeline from Auth -> Route -> Orchestrator -> MockEngine -> Response
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "novalm-test",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True # SSE
            },
            headers={"X-API-Key": "test-key"}
        )
        
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        
        # Check content roughly
        content = response.text
        assert "data: " in content
        assert "[DONE]" in content

@pytest.mark.skip(reason="Rate limit test takes time/state dependent")
def test_rate_limit():
    # Simple check if rate limit triggers. 
    # Depends on how many requests we spam.
    # Rate limit default is 60 RPM.
    headers = {"X-API-Key": "test-key"}
    payload = {
        "model": "novalm-test",
        "messages": [{"role": "user", "content": "Hello"}] 
    }
    
    # Spam 61 requests
    # Note: TestClient shares state? Middleware uses client.host usually 'testclient'.
    count = 0
    for _ in range(65):
        r = client.post("/v1/chat/completions", json=payload, headers=headers)
        if r.status_code == 429:
            count += 1
            break
            
    assert count > 0
