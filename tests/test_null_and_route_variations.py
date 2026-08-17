import pytest
from fastapi.testclient import TestClient
from main import app, kernel_manager, API_KEY, sanitize_id, _get_effective_session_id, CodeRequest
from unittest.mock import patch, MagicMock

client = TestClient(app)
headers = {"X-API-Key": API_KEY}

def test_sanitize_id_null_strings():
    assert sanitize_id("null") == ""
    assert sanitize_id("NULL") == ""
    assert sanitize_id("undefined") == ""
    assert sanitize_id("None") == ""
    assert sanitize_id("none") == ""
    assert sanitize_id("valid123_id") == "valid123_id"

def test_get_effective_session_id_null_fallbacks():
    # Reset LAST_UPLOADED_SESSION_ID for testing pure fallback
    import main
    main.LAST_UPLOADED_SESSION_ID = None

    req = CodeRequest(code="print(1)", session_id="null")
    assert _get_effective_session_id(req) is None

    req_user = CodeRequest(code="print(1)", session_id="undefined", user_id="user123")
    assert _get_effective_session_id(req_user) == "user_user123"

def test_cross_session_download_ids_resolution():
    kernel_manager.file_id_map.clear()
    kernel_manager.nanoid_to_session.clear()
    kernel_manager.session_to_nanoid.clear()

    real_sid, nanoid_sid = kernel_manager.get_or_create_session_mapping("session_alpha")
    file_map = kernel_manager.get_file_id_mapping(nanoid_sid, ["report.pdf"])
    file_id = file_map["report.pdf"]

    # Download request with 'null' session_id should resolve to session_alpha and real_filename 'report.pdf'
    res_sid, res_file = kernel_manager.resolve_download_ids("null", file_id)
    assert res_sid == real_sid
    assert res_file == "report.pdf"

    # Download request with mismatched session_id should also resolve cross-session
    res_sid2, res_file2 = kernel_manager.resolve_download_ids("mismatched_session", file_id)
    assert res_sid2 == real_sid
    assert res_file2 == "report.pdf"

def test_route_variations_upload_and_exec():
    with patch("main.DOCKER_CLIENT") as mock_docker:
        mock_container = MagicMock()
        mock_container.exec_run.return_value = MagicMock(exit_code=0, output=(b"output_text\n", b""))
        mock_docker.containers.run.return_value = mock_container

        # Exec route variations
        for route in ["/exec", "/run/exec"]:
            res = client.post(route, json={"code": "print('hello')", "session_id": "null"}, headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert data["session_id"] != "null"
            assert len(data["session_id"]) == 21
            assert data["stdout"] == "output_text\n"
            assert data["files"] is not None
            assert data["images"] is not None
            assert None not in data.values()

        # Upload route variations
        upload_routes = [
            "/upload",
            "/run/upload",
            "/files/upload",
            "/api/upload",
            "/api/files/upload",
            "/api/files/code/upload",
            "/files/code/upload",
        ]
        files = [("files", ("test_file.txt", b"content", "text/plain"))]
        for route in upload_routes:
            res = client.post(route, data={"session_id": "null"}, files=files, headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert data["session_id"] != "null"
            assert len(data["session_id"]) == 21
            assert data["message"] == "success"

def test_download_route_variations_and_query_params():
    with patch("main.kernel_manager.download_file") as mock_dl:
        mock_dl.return_value = (b"file content bytes", 123456789)

        # Setup mapping in kernel_manager
        real_sid, nanoid_sid = kernel_manager.get_or_create_session_mapping("session_beta")
        file_map = kernel_manager.get_file_id_mapping(nanoid_sid, ["data.csv"])
        file_id = file_map["data.csv"]

        download_path_routes = [
            f"/api/files/code/download/{nanoid_sid}/{file_id}",
            f"/files/code/download/{nanoid_sid}/{file_id}",
            f"/api/code/download/{nanoid_sid}/{file_id}",
            f"/code/download/{nanoid_sid}/{file_id}",
            f"/download/{nanoid_sid}/{file_id}",
            f"/run/download/{nanoid_sid}/{file_id}",
            f"/files/download/{nanoid_sid}/{file_id}",
            f"/api/files/download/{nanoid_sid}/{file_id}",
        ]

        for route in download_path_routes:
            res = client.get(route, headers=headers)
            assert res.status_code == 200
            assert res.content == b"file content bytes"

        # Query param variations
        query_routes = [
            "/download",
            "/run/download",
            "/files/download",
            "/api/download",
            "/api/files/download",
            "/api/files/code/download",
            "/files/code/download",
        ]

        for route in query_routes:
            # session_id & file_id query
            res = client.get(f"{route}?session_id={nanoid_sid}&file_id={file_id}", headers=headers)
            assert res.status_code == 200
            assert res.content == b"file content bytes"

            # session_id="null" & file_id query
            res_null = client.get(f"{route}?session_id=null&file_id={file_id}", headers=headers)
            assert res_null.status_code == 200
            assert res_null.content == b"file content bytes"

if __name__ == "__main__":
    pytest.main([__file__])
