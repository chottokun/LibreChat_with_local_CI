import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from main import app, kernel_manager, API_KEY

client = TestClient(app)

def test_deep_directory_file_listing_behavior():
    """RCEサンドボックス内でサブディレクトリにファイルが生成された場合の現状の挙動を検証。"""
    headers = {"X-API-Key": API_KEY}
    
    # モック: list_files が os.listdir の挙動（直下のみ）を返す場合
    with patch.object(kernel_manager, "execute_code") as mock_exec, \
         patch.object(kernel_manager, "list_files") as mock_list, \
         patch.object(kernel_manager, "get_file_id_mapping") as mock_map:
        
        mock_exec.return_value = {"stdout": "created", "stderr": "", "exit_code": 0}
        # /mnt/data には root_file.txt と deep_dir (フォルダ) が存在
        mock_list.return_value = ["root_file.txt", "deep_dir"]
        mock_map.return_value = {"root_file.txt": "nanoid_root_file_21c", "deep_dir": "nanoid_deep_dir_21ch"}

        response = client.post(
            "/exec",
            headers=headers,
            json={
                "code": "import os; os.makedirs('deep_dir', exist_ok=True); open('deep_dir/sub.png', 'w').write('data')",
                "language": "python"
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        filenames = [f["name"] for f in data["files"]]
        # /mnt/data 直下のエントリが取得され、ルート直下のファイルが適切に一覧化されることを確認
        assert "root_file.txt" in filenames
        assert "deep_dir/sub.png" not in filenames
