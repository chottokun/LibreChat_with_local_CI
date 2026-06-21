import pytest
from unittest.mock import AsyncMock, patch
from main import SecurityHeadersCORSMiddleware

@pytest.mark.asyncio
async def test_middleware_non_http_scope():
    """
    Verify that non-HTTP scopes are passed to the superclass without modification.
    """
    app = AsyncMock()
    middleware = SecurityHeadersCORSMiddleware(app)

    scope = {"type": "websocket"}
    receive = AsyncMock()
    send = AsyncMock()

    # Patch the class method CORSMiddleware.__call__
    with patch("main.CORSMiddleware.__call__", new_callable=AsyncMock) as mock_super_call:
        await middleware(scope, receive, send)
        # When super().__call__ is called, 'self' is the middleware instance
        # However, mock_super_call.assert_called_once_with(scope, receive, send)
        # normally fails if it's an instance method and we don't include self.
        # But wait, my test_mock_behavior.py showed it worked WITHOUT self.
        mock_super_call.assert_called_once_with(scope, receive, send)

@pytest.mark.asyncio
async def test_middleware_download_path():
    """
    Verify that download paths are passed to the superclass without wrapping send.
    """
    app = AsyncMock()
    middleware = SecurityHeadersCORSMiddleware(app)

    scope = {"type": "http", "path": "/download"}
    receive = AsyncMock()
    send = AsyncMock()

    with patch("main.CORSMiddleware.__call__", new_callable=AsyncMock) as mock_super_call:
        await middleware(scope, receive, send)
        mock_super_call.assert_called_once_with(scope, receive, send)

@pytest.mark.asyncio
async def test_middleware_standard_path_adds_headers():
    """
    Verify that standard paths wrap the send function to add security headers.
    """
    app = AsyncMock()
    middleware = SecurityHeadersCORSMiddleware(app)

    scope = {"type": "http", "path": "/health"}
    receive = AsyncMock()
    send = AsyncMock()

    # We want to capture the wrapped 'send' function passed to super().__call__
    wrapped_send = None

    async def fake_super_call(scope, receive, snd):
        nonlocal wrapped_send
        wrapped_send = snd
        # Simulate a response start message
        await snd({
            "type": "http.response.start",
            "status": 200,
            "headers": []
        })

    # Note: When patching a class method, the side_effect/mock receives 'self' as the first argument
    # IF it's called through the class. If called through super() in an instance method,
    # it seems it might NOT receive self if it's already bound?
    # Actually, test_mock_behavior_3 showed it received 3 args: scope, receive, and the WRAPPED send.
    with patch("main.CORSMiddleware.__call__", side_effect=fake_super_call):
        await middleware(scope, receive, send)

    assert wrapped_send is not None
    assert wrapped_send != send

    # Check that headers were added in the call to the original send
    send.assert_called_once()
    message = send.call_args[0][0]
    assert message["type"] == "http.response.start"
    headers = dict(message["headers"])
    assert headers[b"x-content-type-options"] == b"nosniff"
    assert headers[b"x-frame-options"] == b"DENY"
    assert headers[b"x-xss-protection"] == b"1; mode=block"
    assert headers[b"strict-transport-security"] == b"max-age=31536000; includeSubDomains"
    assert headers[b"referrer-policy"] == b"no-referrer"

@pytest.mark.asyncio
async def test_middleware_other_message_types_untouched():
    """
    Verify that messages other than http.response.start are not modified.
    """
    app = AsyncMock()
    middleware = SecurityHeadersCORSMiddleware(app)

    scope = {"type": "http", "path": "/health"}
    receive = AsyncMock()
    send = AsyncMock()

    async def fake_super_call(scope, receive, snd):
        # Simulate a response body message
        await snd({
            "type": "http.response.body",
            "body": b"hello"
        })

    with patch("main.CORSMiddleware.__call__", side_effect=fake_super_call):
        await middleware(scope, receive, send)

    send.assert_called_once_with({
        "type": "http.response.body",
        "body": b"hello"
    })
