import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException
import main
from main import app, get_api_key
from unittest.mock import patch

client = TestClient(app)

@pytest.mark.asyncio
async def test_get_api_key_invalid():
    with pytest.raises(HTTPException) as excinfo:
        await get_api_key(api_key="wrong_key")
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Invalid API Key"

@pytest.mark.asyncio
async def test_get_api_key_valid():
    result = await get_api_key(api_key=main.API_KEY)
    assert result == main.API_KEY

def test_run_endpoint_no_auth():
    response = client.post("/run", json={"code": "print('hello')", "session_id": "test"})
    # FastAPI returns 401 Unauthorized when APIKeyHeader is missing and auto_error=True
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"

def test_run_endpoint_invalid_auth():
    response = client.post(
        "/run",
        json={"code": "print('hello')", "session_id": "test"},
        headers={"X-API-Key": "wrong_key"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API Key"

@patch("main.kernel_manager.execute_code")
def test_run_endpoint_valid_auth(mock_execute):
    mock_execute.return_value = {"stdout": "hello\n", "stderr": "", "exit_code": 0}
    response = client.post(
        "/run",
        json={"code": "print('hello')", "session_id": "test"},
        headers={"X-API-Key": main.API_KEY}
    )
    assert response.status_code == 200
    assert response.json()["stdout"] == "hello\n"
