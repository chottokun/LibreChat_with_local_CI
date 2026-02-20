# LibreChat Code Interpreter: "True Finish" Integration Guide

This document explains the critical, undocumented requirements to achieve a seamless Code Interpreter integration with LibreChat, specifically focusing on native UI file attachments and reliable downloads.

## 1. The ID Format Requirement (CRITICAL)

LibreChat has strict internal validation for file downloads that is not immediately obvious. When the LibreChat frontend requests a file download, it calls an internal backend route: `/api/files/code/download/{session_id}/{fileId}`.

### The `isValidID` Trap
LibreChat's backend uses an `isValidID()` function to validate both the `session_id` and the `fileId`. This function uses the following regex:
```javascript
/^[A-Za-z0-9_-]{21}$/
```
**This means your IDs must be exactly 21-character alphanumeric nanoids**. 
- Standard UUIDs (36 characters) will be rejected with a `400 Bad Request`.
- Filenames containing dots (e.g., `image.png`) will be rejected.

### The Solution: Nanoid Mapping
Your custom Code Interpreter API **must** return 21-character nanoids in the `/exec` response for both `session_id` and the `id` field of each file attachment. 

Your API must then maintain a mapping system:
1. When LibreChat's backend requests `/download/{nanoid_session}/{nanoid_file}`, your API receives it.
2. Your API translates `{nanoid_session}` back to your internal actual UUID container session.
3. Your API translates `{nanoid_file}` back to the actual filename (e.g., `image.png`).
4. Your API serves the file.

## 2. Nginx Reverse Proxy is NOT Required

A common misconception is that you need an Nginx proxy to intercept `/api/files/code/download/` requests from the browser and send them to your Code Interpreter API. **This is incorrect and will cause 502 Bad Gateway errors.**

LibreChat's architecture handles this internally:
1. Browser requests `/api/files/code/download/session/file` from LibreChat (port 3080).
2. LibreChat's Node.js backend receives the request.
3. LibreChat's backend internally connects to your Code Interpreter API using the `LIBRECHAT_CODE_BASEURL` environment variable.
4. LibreChat's backend streams the file back to the browser.

You only need to ensure `LIBRECHAT_CODE_BASEURL` is correctly set in your `docker-compose.yml` to point to your API container (e.g., `http://code-interpreter-api:8000`).

## 3. Required API Response Schema

To make files appear as native, clickable attachment icons in the chat UI, your `/exec` endpoint must return a structured `files` array matching this schema:

```json
{
  "stdout": "...",
  "stderr": "...",
  "exit_code": 0,
  "session_id": "JYaZO0meBUqiREYVlIP0v", // Must be 21-char nanoid
  "files": [
    {
      "id": "uYj2Ykhc025YgKf3YVE2T", // Must be 21-char nanoid
      "name": "example.png",
      "url": "/api/files/code/download/JYaZO0meBUqiREYVlIP0v/uYj2Ykhc025YgKf3YVE2T",
      "type": "image/png"
    }
  ]
}
```

By adhering to these three rules (Nanoid format, no Nginx proxy, structural schema), your custom Code Interpreter will integrate flawlessly with LibreChat.
