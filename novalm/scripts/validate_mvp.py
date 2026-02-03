import asyncio
import aiohttp
import json
import sys
import time

API_URL = "http://localhost:8000/v1/chat/completions"
API_KEY = "test-key"

async def run_scenario(name: str, payload: dict):
    print(f"\n\n=== RUNNING SCENARIO: {name} ===")
    print(f"Prompt: {payload['messages'][0]['content']}")
    
    start_time = time.time()
    seen_states = set()
    completed = False
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(API_URL, json=payload, headers={"X-API-Key": API_KEY}) as response:
                if response.status != 200:
                    print(f"Error: HTTP {response.status}")
                    text = await response.text()
                    print(text)
                    return False
                
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if line.startswith("data: ") and line != "data: [DONE]":
                        json_str = line[6:]
                        try:
                            chunk = json.loads(json_str)
                            delta = chunk["choices"][0]["delta"]
                            content = delta.get("content", "")
                            
                            # Detect States
                            if "--- ROLE:" in content or "--- PHASE:" in content:
                                print(f"{content.strip()}")
                                seen_states.add(content.strip())
                            elif "[System:" in content:
                                print(f"{content.strip()}")
                                if "Task Completed Successfully" in content or "Research Concluded" in content:
                                    completed = True
                            # Optional: print(content, end="", flush=True) for full debug
                            
                        except Exception:
                            pass
        except Exception as e:
            print(f"Connection Error: {e}")
            return False

    duration = time.time() - start_time
    print(f"\n--- RESULT: {name} ---")
    print(f"Duration: {duration:.2f}s")
    print(f"States Triggered: {len(seen_states)}")
    print(f"Status: {'PASS' if completed else 'FAIL'}")
    return completed

async def main():
    # 1. Autonomous Coding Agent Scenario
    coding_payload = {
        "model": "novalm-v1",
        "messages": [{"role": "user", "content": "Create a python script called fib.py that prints the first 10 fibonacci numbers."}],
        "sampling_params": {"preset": "autonomous"},
        # We need generic tools for agent to work
        "tools": [
            {"type": "function", "function": {"name": "write_file", "parameters": {"type": "object", "properties": {"filename": {"type": "string"}, "content": {"type": "string"}}}}},
            {"type": "function", "function": {"name": "python_exec", "parameters": {"type": "object", "properties": {"code": {"type": "string"}}}}}
        ]
    }

    # 2. Research Agent Scenario
    research_payload = {
        "model": "novalm-v1",
        "messages": [{"role": "user", "content": "Why is deep learning effective for NLP?"}],
        "sampling_params": {"preset": "research"},
         "tools": [
            {"type": "function", "function": {"name": "pdf_reader", "parameters": {"type": "object", "properties": {"filename": {"type": "string"}}}}},
            {"type": "function", "function": {"name": "python_exec", "parameters": {"type": "object", "properties": {"code": {"type": "string"}}}}}
        ]
    }

    print("Checking Server Availability...")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get("http://localhost:8000/metrics") as resp:
                if resp.status != 200:
                    print("Server not ready.")
                    sys.exit(1)
        except:
             print("Server not running at http://localhost:8000. Please start it first.")
             sys.exit(1)

    pass_1 = await run_scenario("Autonomous Agent (Coding)", coding_payload)
    pass_2 = await run_scenario("Research Agent (Science)", research_payload)
    
    if pass_1 and pass_2:
        print("\n\n>>> ALL VALIDATION TESTS PASSED <<<")
        sys.exit(0)
    else:
        print("\n\n>>> VALIDATION FAILED <<<")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
