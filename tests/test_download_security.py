import pytest
import os
from fastapi.testclient import TestClient
from main import app, kernel_manager, API_KEY

client = TestClient(app)

def test_download_with_empty_sanitized_session_id():
    # ID consisting only of characters that get sanitized away
    session_id = "@@@"
    filename = "test.txt"
    headers = {"X-API-Key": API_KEY}

    response = client.get(f"/download/{session_id}/{filename}", headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid session ID"

def test_download_path_traversal_with_volume_mounting(tmp_path):
    # Setup: Use a temporary directory for RCE_DATA_DIR_INTERNAL
    test_data_dir = str(tmp_path / "sessions")
    os.makedirs(test_data_dir, exist_ok=True)

    # Create a file outside the data directory
    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("sensitive")

    # We need to mock RCE_DATA_DIR_INTERNAL and RCE_DATA_DIR_HOST
    # but they are module-level constants in main.py.
    # We can try to patch them or use the fact that they might be configurable.

    import main
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(main, "RCE_DATA_DIR_INTERNAL", str(test_data_dir))
        mp.setattr(main, "RCE_DATA_DIR_HOST", "/some/host/path")

        # Inject a malicious mapping that bypasses sanitization (internal UUID can be anything technically if we force it)
        with kernel_manager.lock:
            # Construct a path that points outside
            # filepath = os.path.join(session_dir, real_filename)
            # session_dir = os.path.join(RCE_DATA_DIR_INTERNAL, real_session_id)
            kernel_manager.nanoid_to_session["attacker"] = "../.."

        headers = {"X-API-Key": API_KEY}
        # Try to download something that would resolve to outside_file if traversal worked
        # filepath = /tmp/pytest-of-jules/pytest-XXX/sessions/../../outside.txt
        response = client.get("/download/attacker/outside.txt", headers=headers)

        assert response.status_code == 403
        assert response.json()["detail"] == "Forbidden"

if __name__ == "__main__":
    pytest.main([__file__])
