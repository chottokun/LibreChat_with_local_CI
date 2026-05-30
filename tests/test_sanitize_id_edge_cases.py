import pytest
from main import sanitize_id

def test_sanitize_id_none():
    """
    引数に None が渡された場合（ランタイムでの想定外データ等）、
    早期リターンによって空文字列 "" が返ることを検証します。
    """
    assert sanitize_id(None) == ""

def test_sanitize_id_empty_string():
    """引数が空文字列 "" の場合、空文字列 "" が返ることを検証します。"""
    assert sanitize_id("") == ""

def test_sanitize_id_all_invalid_chars():
    """
    記号等の無効な文字のみで構成される文字列が渡された場合、
    文字の抽出ループを経た結果として空文字列 "" が返ることを検証します。
    """
    assert sanitize_id("!@#$%^&*()") == ""

def test_sanitize_id_mixed_valid_invalid():
    """
    有効な文字と無効な文字が混在している場合、
    無効な文字のみが完全に除去され、有効な文字のみが維持されることを検証します。
    """
    assert sanitize_id("valid-id_123!@#") == "valid-id_123"

def test_sanitize_id_only_valid():
    """
    英数字、ハイフン、アンダースコアなどの有効な文字のみで構成される場合、
    文字列が一切変更されずにそのまま返ることを検証します。
    """
    assert sanitize_id("abcABC123-_") == "abcABC123-_"
