#!/bin/bash
BASE_URL="http://localhost:8000"
API_KEY="your_secret_key"
PASS=0
FAIL=0

check() {
  local name="$1"
  local expected="$2"
  local actual="$3"
  if echo "$actual" | grep -qF "$expected"; then
    echo "✅ PASS: $name"
    PASS=$((PASS+1))
  else
    echo "❌ FAIL: $name"
    echo "   Expected to contain: $expected"
    echo "   Got: $actual"
    FAIL=$((FAIL+1))
  fi
}

echo "=== Code Interpreter API Integration Tests ==="
echo ""

# Test 1: Health check
echo "[1/8] Health check..."
r=$(curl -sf "$BASE_URL/health" --max-time 5)
check "Health check" '"status":"ok"' "$r"

# Test 2: Auth rejection
echo "[2/8] Auth rejection..."
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/exec" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: wrong_key" \
  -d '{"code":"print(1)","lang":"py"}' --max-time 5)
check "Auth rejection (401)" "401" "$code"

# Test 3: Basic Python
echo "[3/8] Basic Python execution (2+2)..."
r=$(curl -sf -X POST "$BASE_URL/exec" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"session_id":"integ-basic","code":"print(2+2)","lang":"py"}' --max-time 60)
check "Basic Python (stdout contains 4)" '4' "$r"
check "Basic Python (exit_code 0)" '"exit_code":0' "$r"

# Test 4: Filesystem persistence (write file, read in next call)
echo "[4/8] Filesystem persistence (write then read)..."
curl -sf -X POST "$BASE_URL/exec" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"session_id":"integ-persist","code":"with open(\"state.txt\",\"w\") as f: f.write(\"hello_persist\")","lang":"py"}' --max-time 60 > /dev/null
r=$(curl -sf -X POST "$BASE_URL/exec" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"session_id":"integ-persist","code":"print(open(\"state.txt\").read())","lang":"py"}' --max-time 60)
check "Filesystem persistence (file readable)" 'hello_persist' "$r"

# Test 5: Numpy available
echo "[5/8] Numpy library available..."
r=$(curl -sf -X POST "$BASE_URL/exec" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"session_id":"integ-numpy","code":"import numpy as np; print(np.sqrt(9))","lang":"py"}' --max-time 60)
check "Numpy sqrt(9)=3.0" '3.0' "$r"

# Test 6: Pandas available
echo "[6/8] Pandas library available..."
r=$(curl -sf -X POST "$BASE_URL/exec" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"session_id":"integ-pandas","code":"import pandas as pd; df=pd.DataFrame({\"a\":[1,2,3]}); print(df[\"a\"].sum())","lang":"py"}' --max-time 60)
check "Pandas sum=6" '6' "$r"

# Test 7: Error handling (syntax error captured)
echo "[7/8] Error handling (syntax error)..."
r=$(curl -sf -X POST "$BASE_URL/exec" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"session_id":"integ-err","code":"def broken(: pass","lang":"py"}' --max-time 60)
check "Syntax error in stderr" 'SyntaxError' "$r"
check "Syntax error exit_code=1" '"exit_code":1' "$r"

# Test 8: File listing endpoint
echo "[8/8] File listing endpoint..."
r=$(curl -sf -H "X-API-Key: $API_KEY" "$BASE_URL/files/integ-persist" --max-time 10)
check "File listing contains state.txt" 'state.txt' "$r"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ $FAIL -eq 0 ] && exit 0 || exit 1
