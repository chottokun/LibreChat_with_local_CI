import pytest
from unittest.mock import patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from main import app, API_KEY, kernel_manager

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_kernel_manager():
    """テスト実行前に KernelManager のマッピング状態をクリアします。"""
    with kernel_manager.lock:
        kernel_manager.active_kernels.clear()
        kernel_manager.nanoid_to_session.clear()
        kernel_manager.session_to_nanoid.clear()
        kernel_manager.file_id_map.clear()
    yield

@patch("main.kernel_manager.list_files")
def test_list_files_success(mock_list_files):
    # Mock return value for list_files
    expected_files = ["data.csv", "script.py", "output/results.json"]
    mock_list_files.return_value = expected_files

    session_id = "test_session_123"
    response = client.get(
        f"/files/{session_id}",
        headers={"X-API-Key": API_KEY}
    )

    assert response.status_code == 200
    # The API returns a list of dictionaries with filename, fileId, and id
    json_response = response.json()
    assert isinstance(json_response, list)
    assert len(json_response) == len(expected_files)
    for i, f in enumerate(expected_files):
        assert json_response[i]["filename"] == f
    assert "fileId" in json_response[0]
    mock_list_files.assert_called_once_with(session_id, external_session_id=session_id)

@patch("main.kernel_manager.list_files")
def test_list_files_unauthorized(mock_list_files):
    session_id = "test_session_123"
    with patch("main.DISABLE_AUTH", False):
        response = client.get(
            f"/files/{session_id}",
            headers={"X-API-Key": "wrong_key"}
        )
        assert response.status_code == 401

@patch("main.kernel_manager.list_files")
def test_list_files_empty(mock_list_files):
    # Mock return value for an empty session
    mock_list_files.return_value = []

    session_id = "empty_session"
    response = client.get(
        f"/files/{session_id}",
        headers={"X-API-Key": API_KEY}
    )

    assert response.status_code == 200
    assert response.json() == []
    mock_list_files.assert_called_once_with(session_id, external_session_id=session_id)


@patch("main.kernel_manager.list_files")
def test_list_files_sanitization(mock_list_files):
    """
    セッションIDに特殊文字（例: $）が含まれている場合に、
    sanitize_id により適切に除去・サニタイズされて処理されることを検証します。
    """
    mock_list_files.return_value = []
    session_id = "session$123"
    sanitized_id = "session123"

    response = client.get(
        f"/files/{session_id}",
        headers={"X-API-Key": API_KEY}
    )

    assert response.status_code == 200
    mock_list_files.assert_called_once_with(sanitized_id, external_session_id=sanitized_id)


@patch("main.kernel_manager.list_files")
def test_list_files_nanoid_resolution(mock_list_files):
    """
    LibreChatで使用される Nanoid 形式のセッションIDが与えられた場合に、
    KernelManager の nanoid_to_session マップによって本物の UUID セッションIDに
    正しく解決されて kernel_manager.list_files が呼び出されることを検証します。
    """
    mock_list_files.return_value = []
    nanoid_session = "nanoid_session_id"
    internal_uuid = "uuid_session_id"

    with kernel_manager.lock:
        kernel_manager.nanoid_to_session[nanoid_session] = internal_uuid
        kernel_manager.session_to_nanoid[internal_uuid] = nanoid_session

    response = client.get(
        f"/files/{nanoid_session}",
        headers={"X-API-Key": API_KEY}
    )

    assert response.status_code == 200
    # list_files の第1引数は本物の UUID であるべきですが、external_session_id は NanoID のままである必要があります
    mock_list_files.assert_called_once_with(internal_uuid, external_session_id=nanoid_session)


@patch("main.kernel_manager.list_files")
def test_list_files_with_id_mapping(mock_list_files):
    """
    file_id_map にファイル名とランダムな ID のマッピングが存在する場合に、
    返されるファイル一覧の各エントリに、元のファイル名に対応する fileId および id が
    正しくマッピングされてレスポンスが生成されることを検証します。
    """
    session_id = "test_session"
    filenames = ["file1.txt", "file2.csv"]
    mock_list_files.return_value = filenames

    file_id_1 = "id_file_1"
    file_id_2 = "id_file_2"

    with kernel_manager.lock:
        kernel_manager.file_id_map[session_id] = {
            file_id_1: filenames[0],
            file_id_2: filenames[1]
        }

    response = client.get(
        f"/files/{session_id}",
        headers={"X-API-Key": API_KEY}
    )

    assert response.status_code == 200
    json_response = response.json()
    assert len(json_response) == 2

    # ファイル名に対する ID が正しく解決されているかアサート
    file1_entry = next(f for f in json_response if f["filename"] == "file1.txt")
    assert file1_entry["fileId"] == file_id_1
    assert file1_entry["id"] == file_id_1

    file2_entry = next(f for f in json_response if f["filename"] == "file2.csv")
    assert file2_entry["fileId"] == file_id_2
    assert file2_entry["id"] == file_id_2


@patch("main.kernel_manager.list_files")
def test_list_files_http_exception(mock_list_files):
    """Verifies that HTTPException is propagated."""
    mock_list_files.side_effect = HTTPException(status_code=507, detail="Insufficient storage")

    session_id = "test_session"
    response = client.get(
        f"/files/{session_id}",
        headers={"X-API-Key": API_KEY}
    )

    assert response.status_code == 507
    assert response.json()["detail"] == "Insufficient storage"


@patch("main.kernel_manager.list_files")
def test_list_files_generic_exception(mock_list_files, caplog):
    """Verifies that generic exceptions return 500 and are logged."""
    mock_list_files.side_effect = Exception("Unexpected error")

    session_id = "test_session"
    response = client.get(
        f"/files/{session_id}",
        headers={"X-API-Key": API_KEY}
    )

    assert response.status_code == 500
    assert "Unexpected error" in response.json()["detail"]
    assert "Error listing session files" in caplog.text
