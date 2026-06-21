import threading
import weakref
from main import WeakrefRLock

def test_weakref_lock_basic_acquire_release():
    """基本的なロックの取得と解放の機能をテスト。"""
    lock = WeakrefRLock()
    assert lock.acquire() is True
    lock.release()

def test_weakref_lock_context_manager():
    """コンテキストマネージャ（with文）の動作をテスト。"""
    lock = WeakrefRLock()
    with lock:
        # 他のスレッドからは取得できないはず
        def try_acquire(lock_obj, result):
            result.append(lock_obj.acquire(blocking=False))

        res = []
        t = threading.Thread(target=try_acquire, args=(lock, res))
        t.start()
        t.join()
        assert res[0] is False, "コンテキストマネージャ実行中はロックが取得できないこと"

    # 抜けた後は取得できるはず
    assert lock.acquire(blocking=False) is True
    lock.release()

def test_weakref_lock_reentrancy():
    """ロックの再入可能（Re-entrant）特性をテスト。"""
    lock = WeakrefRLock()
    with lock:
        with lock:
            assert lock.acquire(blocking=False) is True
            lock.release()

def test_weakref_lock_thread_isolation():
    """スレッド間でのロックの排他制御をテスト。"""
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

    # 別スレッドがロックを取得するのを待つ
    assert acquired_event.wait(timeout=2) is True

    # メインスレッドからは取得できないこと
    assert lock.acquire(blocking=False) is False

    # ロック解放シグナルを送る
    release_event.set()
    thread_finished.wait(timeout=2)
    t.join()

    # 解放後はメインスレッドで取得できること
    assert lock.acquire(blocking=False) is True
    lock.release()

def test_weakref_lock_weakref_support():
    """WeakrefRLockオブジェクトが弱参照をサポートしていることをテスト。"""
    lock = WeakrefRLock()
    ref = weakref.ref(lock)
    assert ref() is lock
    del lock
    import gc
    gc.collect()
    assert ref() is None

def test_weakref_lock_weak_value_dict():
    """WeakValueDictionary内でWeakrefRLockが正しく機能することをテスト。"""
    d = weakref.WeakValueDictionary()
    lock = WeakrefRLock()
    d["session1"] = lock
    assert d["session1"] is lock

    del lock
    import gc
    gc.collect()
    assert "session1" not in d

def test_weakref_lock_exit_with_exception():
    """コンテキストマネージャ内で例外が発生した場合でもロックが解放されることをテスト。"""
    lock = WeakrefRLock()
    try:
        with lock:
            raise ValueError("Test exception")
    except ValueError:
        pass

    # 例外発生後もロックが解放されていること
    assert lock.acquire(blocking=False) is True
    lock.release()
