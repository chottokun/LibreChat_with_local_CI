import threading
import weakref
import pytest
from main import WeakrefRLock

def test_weakref_lock_basic_acquire_release():
    """Tests basic acquire and release functionality."""
    lock = WeakrefRLock()
    assert lock.acquire() is True
    lock.release()

def test_weakref_lock_context_manager():
    """Tests context manager (with statement) support."""
    lock = WeakrefRLock()
    with lock:
        # Lock should be acquired here
        pass
    # Lock should be released here

def test_weakref_lock_reentrancy():
    """Tests that the lock is re-entrant."""
    lock = WeakrefRLock()
    with lock:
        with lock:
            assert lock.acquire(blocking=False) is True
            lock.release()

def test_weakref_lock_thread_isolation():
    """Tests that the lock provides isolation between threads."""
    lock = WeakrefRLock()
    acquired_event = threading.Event()
    release_event = threading.Event()
    thread_finished = threading.Event()

    def worker():
        with lock:
            acquired_event.set()
            release_event.wait(timeout=2)
        thread_finished.set()

    t = threading.Thread(target=worker)
    t.start()

    # Wait for the thread to acquire the lock
    assert acquired_event.wait(timeout=2) is True

    # Try to acquire the lock in the main thread (should fail or block)
    assert lock.acquire(blocking=False) is False

    # Signal the thread to release the lock
    release_event.set()
    thread_finished.wait(timeout=2)

    # Now the main thread should be able to acquire it
    assert lock.acquire(blocking=False) is True
    lock.release()

def test_weakref_lock_weakref_support():
    """Tests that the WeakrefRLock object can be weak-referenced."""
    lock = WeakrefRLock()
    ref = weakref.ref(lock)
    assert ref() is lock
    del lock
    # Force GC to be sure, though in CPython del might be enough for simple cases
    import gc
    gc.collect()
    assert ref() is None

def test_weakref_lock_weak_value_dict():
    """Tests that WeakrefRLock works correctly in a WeakValueDictionary."""
    d = weakref.WeakValueDictionary()
    lock = WeakrefRLock()
    d["session1"] = lock

    assert d["session1"] is lock

    del lock
    import gc
    gc.collect()

    assert "session1" not in d
