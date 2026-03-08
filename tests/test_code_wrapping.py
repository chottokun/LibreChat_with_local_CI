import main
import ast
from unittest.mock import patch

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

def test_wrap_code_empty_string():
    code = ""
    wrapped = main.wrap_code(code)
    assert wrapped == ""

def test_wrap_code_only_comments():
    code = "# This is a comment\n# Another comment"
    wrapped = main.wrap_code(code)
    assert wrapped == code

def test_wrap_code_multiple_expressions():
    code = "1 + 1\n2 + 2"
    wrapped = main.wrap_code(code)
    # Only the last one should be wrapped
    assert "1 + 1" in wrapped
    assert "__last_res__ = 2 + 2" in wrapped
    assert "print(repr(__last_res__))" in wrapped
    # The first one should NOT be wrapped in __last_res__
    assert "__last_res__ = 1 + 1" not in wrapped

def test_wrap_code_unparse_failure():
    code = "1 + 1"
    with patch("ast.unparse", side_effect=Exception("Unparse failed")):
        wrapped = main.wrap_code(code)
        # Should return original code on exception
        assert wrapped == code
