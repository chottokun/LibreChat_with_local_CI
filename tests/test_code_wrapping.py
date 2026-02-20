import sys
import os
from unittest.mock import MagicMock, patch

# Mock docker before importing main
sys.modules['docker'] = MagicMock()
import main

def test_wrap_code_expression():
    code = "1 + 1"
    wrapped = main.wrap_code(code)
    assert "__last_res__ = 1 + 1" in wrapped
    assert "if __last_res__ is not None:" in wrapped
    assert "print(repr(__last_res__))" in wrapped

def test_wrap_code_multiline_expression():
    code = "x = 10\ny = 20\nx + y"
    wrapped = main.wrap_code(code)
    assert "x = 10" in wrapped
    assert "y = 20" in wrapped
    assert "__last_res__ = x + y" in wrapped
    assert "print(repr(__last_res__))" in wrapped

def test_wrap_code_already_printing():
    code = "print('hello')"
    wrapped = main.wrap_code(code)
    # print() returns None, so __last_res__ will be None,
    # and it won't be printed again.
    assert "__last_res__ = print('hello')" in wrapped
    assert "if __last_res__ is not None:" in wrapped

def test_wrap_code_assignment():
    code = "x = 1"
    wrapped = main.wrap_code(code)
    # Assignment is not an expression, so it should NOT be wrapped
    assert wrapped == code

def test_wrap_code_syntax_error():
    code = "if x ="
    wrapped = main.wrap_code(code)
    assert wrapped == code
