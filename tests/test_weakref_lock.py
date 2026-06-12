import threading
import weakref
import pytest
import os
from unittest.mock import patch

# Set required environment variable for main.py import
os.environ["LIBRECHAT_CODE_API_KEY"] = "test_key"

from main import WeakrefRLock

def test_weakref_lock_context_manager():
    """Test that the context manager correctly acquires and releases the lock."""
    lock = WeakrefRLock()
    with lock:
        # In another thread, try to acquire the lock; it should fail
        def try_acquire(l, result):
            result.append(l.acquire(blocking=False))

        res = []
        t = threading.Thread(target=try_acquire, args=(lock, res))
        t.start()
        t.join()
        assert res[0] is False, "Lock should be held by the context manager"

    # Now it should be acquirable
    assert lock.acquire(blocking=False), "Lock should be released after context manager exit"
    lock.release()

def test_weakref_lock_acquire_release():
    """Test direct acquire and release methods."""
    lock = WeakrefRLock()
    assert lock.acquire() is True
    assert lock.acquire(blocking=False) is True # RLock is re-entrant
    lock.release()
    lock.release()

    # In another thread
    def try_acquire(l, result):
        result.append(l.acquire(blocking=False))

    lock.acquire()
    res = []
    t = threading.Thread(target=try_acquire, args=(lock, res))
    t.start()
    t.join()
    assert res[0] is False, "Lock should be held"
    lock.release()

def test_weakref_lock_reentrancy():
    """Test that the lock is re-entrant as it wraps RLock."""
    lock = WeakrefRLock()
    with lock:
        with lock:
            assert lock.acquire(blocking=False) is True
            lock.release()

def test_weakref_lock_thread_exclusion():
    """Test that the lock correctly excludes other threads."""
    lock = WeakrefRLock()
    acquired = threading.Event()
    release_lock = threading.Event()
    thread_finished = threading.Event()

    def worker():
        with lock:
            acquired.set()
            release_lock.wait()
        thread_finished.set()

    t = threading.Thread(target=worker)
    t.start()

    acquired.wait()
    # Now the lock is held by the thread
    assert not lock.acquire(blocking=False), "Lock should be held by the worker thread"

    release_lock.set()
    thread_finished.wait()
    t.join()

    # Now it should be acquirable
    assert lock.acquire(blocking=False), "Lock should be released after worker thread finishes"
    lock.release()

def test_weakref_lock_weakref_support():
    """Test that the WeakrefRLock instance can be weakly referenced."""
    d = weakref.WeakValueDictionary()
    lock = WeakrefRLock()
    d['test'] = lock
    assert d['test'] is lock

    del lock
    import gc
    gc.collect()
    assert 'test' not in d, "WeakrefRLock should be garbage collected"

def test_weakref_lock_exit_with_exception():
    """Test that the lock is released even if an exception occurs within the context manager."""
    lock = WeakrefRLock()
    try:
        with lock:
            raise ValueError("Test exception")
    except ValueError:
        pass

    # Lock should be released even if an exception occurred
    assert lock.acquire(blocking=False), "Lock should be released despite exception"
    lock.release()
