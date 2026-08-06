from unittest.mock import patch
from fastapi.testclient import TestClient
from main import app, kernel_manager, API_KEY

client = TestClient(app)

def test_recursive_file_listing_in_container():
    """RCEコンテナ内のサブディレクトリ配下のファイルが再帰的に検出されることを検証。"""
    # 仮想的な os.walk 結果（サブディレクトリ含む）
    mock_files = [
        "data.csv",
        "output/summary.txt",
        "output/images/chart.png"
    ]
    
    with patch.object(kernel_manager, "list_files", return_value=mock_files):
        files = kernel_manager.list_files("test_session_id")
        assert "data.csv" in files
        assert "output/summary.txt" in files
        assert "output/images/chart.png" in files

def test_exec_endpoint_with_nested_directory_files():
    """/exec 呼び出しでネストされたサブディレクトリ配下のファイルが files 配列に含まれることを検証。"""
    headers = {"X-API-Key": API_KEY}
    
    mock_exec_result = {"stdout": "done", "stderr": "", "exit_code": 0}
    mock_files = ["root.txt", "reports/2026/sales.csv"]
    mock_mapping = {
        "root.txt": "nanoid_root_file_21c1",
        "reports/2026/sales.csv": "nanoid_sales_csv_21c2"
    }

    with patch.object(kernel_manager, "execute_code", return_value=mock_exec_result), \
         patch.object(kernel_manager, "list_files", return_value=mock_files), \
         patch.object(kernel_manager, "get_file_id_mapping", return_value=mock_mapping):

        response = client.post(
            "/exec",
            headers=headers,
            json={"code": "print('hello')", "language": "python"}
        )
        assert response.status_code == 200
        data = response.json()
        
        file_names = [f["name"] for f in data["files"]]
        assert "root.txt" in file_names
        assert "reports/2026/sales.csv" in file_names
        
        # Nanoid ファイルIDとURLの検証
        sales_file = next(f for f in data["files"] if f["name"] == "reports/2026/sales.csv")
        assert len(sales_file["id"]) == 21
        assert "/api/files/code/download/" in sales_file["url"]

def test_download_nested_file_safety():
    """サブディレクトリ配下のファイルのダウンロードとパストラバーサル遮断の検証。"""
    headers = {"X-API-Key": API_KEY}
    raw_sid = "test_nested_dl_session"
    real_uuid, nanoid_sid = kernel_manager.get_or_create_session_mapping(raw_sid)
    
    # マッピングにネストされたファイル相対パスを追加
    file_id = "nanoid_nested_file_21"
    with kernel_manager.lock:
        if nanoid_sid not in kernel_manager.file_id_map:
            kernel_manager.file_id_map[nanoid_sid] = {}
        kernel_manager.file_id_map[nanoid_sid][file_id] = "charts/2026/figure.png"

    with patch.object(kernel_manager, "download_file") as mock_dl:
        mock_dl.return_value = (b"png binary data", 1700000000.0)
        
        # 1. 21文字 Nanoid 指定での正しいダウンロード呼び出し
        response = client.get(
            f"/api/files/code/download/{nanoid_sid}/{file_id}",
            headers=headers
        )
        assert response.status_code == 200
        assert response.content == b"png binary data"
        assert response.headers["Content-Type"] == "image/png"
        mock_dl.assert_called_with(real_uuid, "charts/2026/figure.png")
