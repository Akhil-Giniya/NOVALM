import asyncio
import aiohttp
import json
import time
import argparse
from typing import List, Dict

API_URL = "http://localhost:8000/v1/chat/completions"
API_KEY = "test-key"

SAMPLE_TASKS = [
    "Write a python function to calculate fibonacci numbers.",
    "Explain the theory of relativity in one sentence.",
    "Write a bash script to list files larger than 100MB.",
    "Draft a hypothesis for improving matrix multiplication.",
    "What is the capital of France?"
]

async def run_agent(session: aiohttp.ClientSession, task_id: int, prompt: str, preset: str = "creative"):
    """
    Runs a single agent task.
    """
    payload = {
        "model": "novalm-v1",
        "messages": [{"role": "user", "content": prompt}],
        "sampling_params": {"preset": preset},
        # "tools": ... (Optional, can add tools if needed)
    }
    
    start_time = time.time()
    try:
        async with session.post(API_URL, json=payload, headers={"X-API-Key": API_KEY}) as response:
            if response.status != 200:
                text = await response.text()
                print(f"[Task {task_id}] Failed: {response.status} - {text}")
                return None
            
            # Streaming response handling
            full_response = ""
            async for line in response.content:
                line = line.decode('utf-8').strip()
                if line.startswith("data: ") and line != "data: [DONE]":
                    data = json.loads(line[6:])
                    content = data["choices"][0]["delta"].get("content", "")
                    if content:
                        full_response += content
            
            duration = time.time() - start_time
            print(f"[Task {task_id}] Completed in {duration:.2f}s. Length: {len(full_response)} chars.")
            return full_response
            
    except Exception as e:
        print(f"[Task {task_id}] Error: {str(e)}")
        return None

async def main(num_agents: int):
    print(f"Starting {num_agents} parallel agents...")
    start_all = time.time()
    
    tasks_to_run = []
    # Round robin assignment of prompts
    for i in range(num_agents):
        prompt = SAMPLE_TASKS[i % len(SAMPLE_TASKS)]
        tasks_to_run.append((i, prompt))
    
    async with aiohttp.ClientSession() as session:
        tasks = [run_agent(session, i, p) for i, p in tasks_to_run]
        results = await asyncio.gather(*tasks)
        
    total_duration = time.time() - start_all
    success_count = sum(1 for r in results if r is not None)
    
    print(f"\n--- Batch Summary ---")
    print(f"Total Agents: {num_agents}")
    print(f"Successful: {success_count}")
    print(f"Total Time: {total_duration:.2f}s")
    print(f"Throughput: {success_count / total_duration:.2f} req/s")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run parallel agent tasks.")
    parser.add_argument("--agents", type=int, default=5, help="Number of parallel agents")
    args = parser.parse_args()
    
    asyncio.run(main(args.agents))
