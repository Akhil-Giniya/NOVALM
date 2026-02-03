import asyncio
import aiohttp
import time
import json
import statistics
import argparse
import sys

# Default Config
API_URL = "http://localhost:8000/v1/chat/completions"
API_KEY = "test-key"
MODEL = "novalm-v1"

async def make_request(session, prompt, request_id):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
        "X-API-Key": API_KEY
    }
    payload = {
        "model": MODEL,
        # A medium length prompt to trigger generation
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "max_tokens": 100 # Generating 100 tokens is good for stats
    }
    
    start_time = time.time()
    ttft = 0
    token_count = 0
    
    try:
        async with session.post(API_URL, headers=headers, json=payload) as response:
            if response.status != 200:
                print(f"Request {request_id} failed: {response.status}")
                return None
                
            async for line in response.content:
                line = line.decode('utf-8').strip()
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    
                    # Calculate TTFT on first chunk
                    if token_count == 0:
                        ttft = time.time() - start_time
                        
                    token_count += 1
                    
    except Exception as e:
        print(f"Request {request_id} error: {e}")
        return None

    end_time = time.time()
    total_latency = end_time - start_time
    
    return {
        "ttft": ttft,
        "total_latency": total_latency,
        "tokens": token_count,
        "throughput": token_count / total_latency if total_latency > 0 else 0
    }

async def benchmark(concurrency, num_requests):
    prompts = [
        "Explain quantum computing in simple terms.",
        "Write a poem about rust (the metal).",
        "What is the capital of France?",
        "Write a python function to sort a list.",
        "Tell me a joke."
    ]
    
    print(f"Starting Benchmark: {num_requests} requests with concurrency {concurrency}...")
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for i in range(num_requests):
            prompt = prompts[i % len(prompts)]
            tasks.append(make_request(session, prompt, i))
            
            # Simple batching control if we want to strictly limit in-flight
            # But asyncio.gather does all at once. For truly limiting concurrency 
            # we'd use a semaphore, but for this script let's assume num_requests ~= batch size for small N
            # or just dump them all if user asks.
            
        results = await asyncio.gather(*tasks)
        
    valid_results = [r for r in results if r is not None]
    
    if not valid_results:
        print("No successful requests.")
        return

    # Calculate Stats
    ttfts = [r["ttft"] for r in valid_results]
    latencies = [r["total_latency"] for r in valid_results]
    throughputs = [r["throughput"] for r in valid_results]
    
    print("\n--- Benchmark Results ---")
    print(f"Successful Requests: {len(valid_results)}/{num_requests}")
    print(f"Avg TTFT (Time to First Token): {statistics.mean(ttfts):.4f}s")
    print(f"P95 TTFT: {statistics.quantiles(ttfts, n=20)[18]:.4f}s") # 19 cuts -> index 18 is 95%
    print(f"Avg End-to-End Latency: {statistics.mean(latencies):.4f}s")
    print(f"Avg Throughput (Tokens/sec/req): {statistics.mean(throughputs):.2f}")
    
    total_tokens = sum(r["tokens"] for r in valid_results)
    total_time = sum(latencies) # Wait, total throughput of system is different
    # System Throughput approx = Total Tokens / (Max End Time - Min Start Time)
    # But for now per-request stats are fine.

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NovaLM Benchmark")
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--requests", type=int, default=10)
    args = parser.parse_args()
    
    asyncio.run(benchmark(args.concurrency, args.requests))
