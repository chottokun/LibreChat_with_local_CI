import asyncio
import aiohttp
import time
import os
import sys

# Test configuration
API_URL = "http://127.0.0.1:8080"
API_KEY = "testkey"
HEADERS = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY,
    "Authorization": f"Bearer {API_KEY}"
}

async def exec_code(session, session_id, code="print('ok')"):
    url = f"{API_URL}/exec"
    payload = {
        "session_id": session_id,
        "code": code
    }
    start = time.time()
    try:
        async with session.post(url, json=payload, headers=HEADERS, timeout=30) as response:
            resp_json = await response.json()
            return response.status, resp_json, time.time() - start
    except Exception as e:
        return 500, str(e), time.time() - start

async def test_normal_load(num_sessions=10):
    print(f"\n--- Testing Normal Load ({num_sessions} concurrent sessions) ---")
    async with aiohttp.ClientSession() as session:
        tasks = []
        for i in range(num_sessions):
            tasks.append(exec_code(session, f"normal_load_{i}"))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, (status, response, time_taken) in enumerate(results):
            if status != 200:
                 print(f"Session normal_load_{i} failed with status {status}: {response}")

        successes = sum(1 for status, _, _ in results if status == 200)
        print(f"Successes: {successes}/{num_sessions}")
        
        avg_time = sum(time for _, _, time in results) / len(results)
        print(f"Average response time: {avg_time:.2f}s")
        assert successes == num_sessions, "Failed normal load test"

async def test_max_sessions(max_limit=3):
    print(f"\n--- Testing Global Session Limit (Expecting rejection after {max_limit}) ---")
    # Note: Requires starting API with RCE_MAX_SESSIONS=3
    async with aiohttp.ClientSession() as session:
        # First fill up the limit
        for i in range(max_limit):
             status, _, _ = await exec_code(session, f"max_sess_{i}")
             assert status == 200, f"Failed to create allowed session {i}"
        
        # Try one more, should fail with 429
        status, response, _ = await exec_code(session, "max_sess_rejected")
        print(f"Over-limit request returned status: {status}")
        print(f"Response: {response}")
        if status == 503:
             print("SUCCESS: Session limit enforced.")
        else:
             print("FAILED: Session limit not enforced or different error.")

async def main():
    test_mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
    
    if test_mode in ['all', 'normal']:
        await test_normal_load(5)
    
    if test_mode in ['all', 'limit']:
        await test_max_sessions(3) # Set API env to RCE_MAX_SESSIONS=3 for this

if __name__ == "__main__":
    asyncio.run(main())
