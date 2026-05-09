import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from open_webui_integration.rce_workspace_tool import Tools
import json
import base64

@pytest.mark.asyncio
async def test_execute_code_basic():
    tool = Tools()
    tool.valves.RCE_API_BASE_URL = "http://localhost:8000"
    tool.valves.RCE_API_KEY = "test-key"

    metadata = {"chat_id": "test-session-123"}
    code = "print('hello')"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "stdout": "hello\n",
        "stderr": "",
        "result": None,
        "files": []
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        result = await tool.execute_code(code=code, __metadata__=metadata)
        
        assert "hello" in result
        mock_post.assert_called_once()
        # Verify it was called with correct URL and headers
        args, kwargs = mock_post.call_args
        assert args[0] == "http://localhost:8000/exec"
        assert kwargs["headers"]["X-Api-Key"] == "test-key"
        assert kwargs["json"]["session_id"] == "test-session-123"
        assert kwargs["json"]["code"] == code

@pytest.mark.asyncio
async def test_execute_code_with_files():
    tool = Tools()
    tool.valves.RCE_API_BASE_URL = "http://localhost:8000"
    
    metadata = {"chat_id": "test-session-file"}
    code = "print('processing file')"
    
    # Mock files as they appear in Open WebUI
    # Open WebUI provides files with 'id', 'filename', etc. 
    # and sometimes content can be retrieved or is already in the metadata.
    # In some versions, __files__ is a list of dicts.
    files = [
        {
            "id": "file-1",
            "filename": "データ.csv",
            "content": base64.b64encode(b"id,name\n1,test").decode('utf-8')
        }
    ]

    mock_upload_response = MagicMock()
    mock_upload_response.status_code = 200
    
    mock_exec_response = MagicMock()
    mock_exec_response.status_code = 200
    mock_exec_response.json.return_value = {
        "stdout": "processing file\n",
        "stderr": "",
        "result": None,
        "files": []
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        # First call for upload, second for exec
        mock_post.side_effect = [mock_upload_response, mock_exec_response]
        
        result = await tool.execute_code(code=code, __metadata__=metadata, __files__=files)
        
        assert "processing file" in result
        assert mock_post.call_count == 2
        
        # Check upload call
        upload_call = mock_post.call_args_list[0]
        assert upload_call[0][0] == "http://localhost:8000/upload"
        assert upload_call[1]["params"]["session_id"] == "test-session-file"
        
@pytest.mark.asyncio
async def test_execute_code_with_images():
    tool = Tools()
    tool.valves.RCE_API_BASE_URL = "http://localhost:8000"
    
    metadata = {"chat_id": "test-session-img"}
    code = "plt.plot([1,2,3])"
    
    mock_exec_response = MagicMock()
    mock_exec_response.status_code = 200
    mock_exec_response.json.return_value = {
        "stdout": "",
        "stderr": "",
        "result": None,
        "files": ["plot.png"]
    }
    
    mock_download_response = MagicMock()
    mock_download_response.status_code = 200
    mock_download_response.content = b"fake-image-binary"

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        
        mock_post.return_value = mock_exec_response
        mock_get.return_value = mock_download_response
        
        result = await tool.execute_code(code=code, __metadata__=metadata)
        
        assert "![plot.png](data:image/png;base64," in result
        assert base64.b64encode(b"fake-image-binary").decode('utf-8') in result
        mock_get.assert_called_once()
        assert "plot.png" in mock_get.call_args[0][0]
