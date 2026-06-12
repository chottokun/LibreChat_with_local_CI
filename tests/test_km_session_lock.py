import gc
import pytest
from main import KernelManager, WeakrefRLock

def test_get_session_lock_consistency():
    """Verify that multiple calls for the same session_id return the same lock instance."""
    km = KernelManager()
    session_id = "test_session"

    lock1 = km._get_session_lock(session_id)
    lock2 = km._get_session_lock(session_id)

    assert lock1 is lock2
    assert isinstance(lock1, WeakrefRLock)

def test_get_session_lock_isolation():
    """Verify that calls for different session_ids return different lock instances."""
    km = KernelManager()

    lock1 = km._get_session_lock("session1")
    lock2 = km._get_session_lock("session2")

    assert lock1 is not lock2

def test_get_session_lock_interface():
    """Verify that the returned object has acquire and release methods."""
    km = KernelManager()
    lock = km._get_session_lock("test")

    assert hasattr(lock, 'acquire')
    assert hasattr(lock, 'release')

    # Verify it actually works
    assert lock.acquire()
    lock.release()

def test_get_session_lock_weakref_behavior():
    """Verify that the session_locks dictionary clears itself when references are dropped."""
    km = KernelManager()
    session_id = "temp_session"

    # 1. Create a lock and keep a reference
    lock = km._get_session_lock(session_id)
    assert session_id in km.session_locks

    # 2. Drop the reference and force garbage collection
    del lock
    gc.collect()

    # 3. Verify it's gone from the dictionary
    # Note: WeakValueDictionary might not be immediately empty depending on GC timing,
    # but in CPython gc.collect() usually does the trick.
    assert session_id not in km.session_locks
