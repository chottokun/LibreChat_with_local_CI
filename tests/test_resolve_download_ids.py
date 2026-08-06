import pytest
from main import KernelManager

@pytest.fixture
def km():
    manager = KernelManager()
    manager.nanoid_to_session = {}
    manager.session_to_nanoid = {}
    manager.file_id_map = {}
    return manager

def test_resolve_download_ids_both_nanoids(km):
    """Scenario 1: Both session and file IDs are Nanoids and have mappings."""
    km.nanoid_to_session["nano-session"] = "real-session-uuid"
    km.session_to_nanoid["real-session-uuid"] = "nano-session"
    km.file_id_map["nano-session"] = {"nano-file": "real-file.txt"}

    real_session, real_file = km.resolve_download_ids("nano-session", "nano-file")

    assert real_session == "real-session-uuid"
    assert real_file == "real-file.txt"

def test_resolve_download_ids_session_nanoid_file_real(km):
    """Scenario 2: Session ID has mapping, but file name is a real file name (no mapping)."""
    km.nanoid_to_session["nano-session"] = "real-session-uuid"
    km.session_to_nanoid["real-session-uuid"] = "nano-session"
    km.file_id_map["nano-session"] = {}

    real_session, real_file = km.resolve_download_ids("nano-session", "real-file.txt")

    assert real_session == "real-session-uuid"
    assert real_file == "real-file.txt"

def test_resolve_download_ids_session_real_file_nanoid(km):
    """Scenario 3: Session ID is already a real ID (present in session_to_nanoid)."""
    km.session_to_nanoid["real-session-uuid"] = "nano-session"
    km.nanoid_to_session["nano-session"] = "real-session-uuid"
    km.file_id_map["nano-session"] = {"nano-file": "real-file.txt"}

    # Input is the real session UUID
    real_session, real_file = km.resolve_download_ids("real-session-uuid", "nano-file")

    assert real_session == "real-session-uuid"
    assert real_file == "real-file.txt"

def test_resolve_download_ids_no_mappings(km):
    """Scenario 4: No mapping exists for either session or file."""
    real_session, real_file = km.resolve_download_ids("unknown-session", "unknown-file.txt")

    assert real_session == "unknown-session"
    assert real_file == "unknown-file.txt"

def test_resolve_download_ids_sanitization(km):
    """Scenario 5: Input IDs contain path traversal characters (verify sanitize_id and os.path.basename usage)."""
    # Assuming sanitize_id removes '../' and '/'
    # os.path.basename('dir/file.txt') -> 'file.txt'

    km.nanoid_to_session["nanosession"] = "real-session"
    km.file_id_map["nanosession"] = {"nanofile": "real-file.txt"}

    # Input with traversal
    real_session, real_file = km.resolve_download_ids("../../nano/session", "dir/nanofile")

    # sanitize_id("../../nano/session") -> "nanosession"
    # os.path.basename("dir/nanofile") -> "nanofile"
    assert real_session == "real-session"
    assert real_file == "real-file.txt"

def test_resolve_download_ids_os_basename_on_result(km):
    """Verify that the final filename is normalized for relative path."""
    km.nanoid_to_session["s"] = "rs"
    km.file_id_map["s"] = {"f": "sub/path/to/real-file.txt"}

    _, real_file = km.resolve_download_ids("s", "f")
    assert real_file == "sub/path/to/real-file.txt"
