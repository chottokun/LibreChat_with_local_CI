from unittest.mock import patch
from fastapi.testclient import TestClient
from main import app, kernel_manager, API_KEY

client = TestClient(app)

def test_deep_directory_file_listing_and_download_behavior():
    """RCEサンドボックス内で深いサブディレクトリにファイルが生成された場合の表示とダウンロードを検証。"""
    headers = {"X-API-Key": API_KEY}
    
    mock_files = ["root_file.txt", "output/subfolder/deep_chart.png"]

    with patch.object(kernel_manager, "execute_code") as mock_exec, \
         patch.object(kernel_manager, "list_files", return_value=mock_files), \
         patch.object(kernel_manager, "download_file", return_value=(b"\x89PNG\r\n\x1a\n", 1700000000.0)):
        
        mock_exec.return_value = {"stdout": "created", "stderr": "", "exit_code": 0}

        response = client.post(
            "/exec",
            headers=headers,
            json={
                "code": "import os; os.makedirs('output/subfolder', exist_ok=True); open('output/subfolder/deep_chart.png', 'w').write('data')",
                "language": "python"
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        filenames = [f["name"] for f in data["files"]]
        assert "root_file.txt" in filenames
        assert "output/subfolder/deep_chart.png" in filenames

        # Verify image capture for deeply nested image
        assert len(data["images"]) == 1
        assert data["images"][0]["name"] == "output/subfolder/deep_chart.png"
        assert data["images"][0]["format"] == "png"
        assert len(data["images"][0]["base64"]) > 0

        # Verify downloading deeply nested file via direct path parameter with slashes
        deep_file_entry = next(f for f in data["files"] if f["name"] == "output/subfolder/deep_chart.png")
        download_url = deep_file_entry["url"] # e.g. /api/files/code/download/{session}/{file_id}
        
        dl_response = client.get(download_url, headers=headers)
        assert dl_response.status_code == 200
        assert dl_response.content == b"\x89PNG\r\n\x1a\n"
        assert dl_response.headers["Content-Type"] == "image/png"
        assert "deep_chart.png" in dl_response.headers["Content-Disposition"]

        # Direct path-based download with subpaths
        direct_dl_response = client.get(
            f"/download/{data['session_id']}/output/subfolder/deep_chart.png",
            headers=headers
        )
        assert direct_dl_response.status_code == 200
        assert direct_dl_response.content == b"\x89PNG\r\n\x1a\n"
