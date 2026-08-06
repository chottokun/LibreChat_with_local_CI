import re
from concurrent.futures import ThreadPoolExecutor
from main import kernel_manager, generate_nanoid

NANOID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{21}$")

def test_nanoid_length_and_format_boundary():
    """様々な長さや形式のセッションIDに対して、21文字Nanoidが正しくマッピングされるかを検証。"""
    test_ids = [
        "a",                           # 1文字
        "12345678901234567890",        # 20文字
        "123456789012345678901",       # 正確に21文字
        "1234567890123456789012",      # 22文字
        "user_12345_very_long_session_identifier_for_testing", # 長い文字列
        "special!@#$%^&*()_+id",       # 特殊文字含む
    ]

    for input_id in test_ids:
        real_uuid_1, nanoid_1 = kernel_manager.get_or_create_session_mapping(input_id)
        
        # 1. 返却された nanoid は必ず21文字であり正規表現を満たす
        assert len(nanoid_1) == 21, f"Failed length check for input {input_id}: got {len(nanoid_1)}"
        assert NANOID_PATTERN.match(nanoid_1), f"Failed pattern check for input {input_id}: got {nanoid_1}"

        # 2. 再度同じ input_id で呼んだ場合、同じ real_uuid と同じ nanoid が返される
        real_uuid_2, nanoid_2 = kernel_manager.get_or_create_session_mapping(input_id)
        assert real_uuid_1 == real_uuid_2, f"UUID changed for input {input_id}"
        assert nanoid_1 == nanoid_2, f"Nanoid changed for input {input_id}"

        # 3. 返却された nanoid_1 で呼び出した場合も、同じ real_uuid と同じ nanoid_1 が返される
        real_uuid_3, nanoid_3 = kernel_manager.get_or_create_session_mapping(nanoid_1)
        assert real_uuid_3 == real_uuid_1
        assert nanoid_3 == nanoid_1

def test_exact_21_char_nanoid_preservation():
    """入力が元々21文字の有効なNanoidである場合、値がそのまま保持されることを検証。"""
    valid_21_nanoid = generate_nanoid()
    assert len(valid_21_nanoid) == 21
    
    real_uuid, returned_nanoid = kernel_manager.get_or_create_session_mapping(valid_21_nanoid)
    assert returned_nanoid == valid_21_nanoid
    assert real_uuid != valid_21_nanoid # 内部UUIDは別途割り当てられる

def test_parallel_session_mapping_consistency():
    """複数スレッドから同時に同じ非21文字IDでアクセスした場合のマッピング一貫性を検証。"""
    target_id = "concurrent_unmapped_session_id_999"
    
    def worker(_):
        return kernel_manager.get_or_create_session_mapping(target_id)

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(worker, range(20)))

    # 全てのスレッドで同じ (real_uuid, nanoid) が取得できているか
    first_uuid, first_nanoid = results[0]
    assert len(first_nanoid) == 21
    
    for r_uuid, r_nanoid in results:
        assert r_uuid == first_uuid
        assert r_nanoid == first_nanoid

def test_download_id_resolution_with_nanoid():
    """resolve_download_idsが21文字Nanoidおよび内部UUIDの両方で正しく動作することを検証。"""
    raw_id = "user_download_test_id"
    real_uuid, nanoid = kernel_manager.get_or_create_session_mapping(raw_id)
    
    # Nanoid を使用した解決
    resolved_uuid_1, resolved_file_1 = kernel_manager.resolve_download_ids(nanoid, "result.csv")
    assert resolved_uuid_1 == real_uuid
    assert resolved_file_1 == "result.csv"

    # 生のIDを使用した解決
    resolved_uuid_2, resolved_file_2 = kernel_manager.resolve_download_ids(raw_id, "result.csv")
    assert resolved_uuid_2 == real_uuid
    assert resolved_file_2 == "result.csv"
