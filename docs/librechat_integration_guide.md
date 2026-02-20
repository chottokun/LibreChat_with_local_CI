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

## 4. Debugging the "Network Error" on File Downloads

Even if you follow the above rules perfectly, you might encounter a persistent issue where clicking the attachment icon results in a LibreChat popup saying "Something went wrong" (or "Network Error"), and the file downloads with a raw 36-character UUID filename instead of the actual filename.

This is caused by a cascade of two distinct issues that must both be resolved:

### Issue A: Axios Stream Instability (Backend)
LibreChat's backend uses `axios` with `responseType: 'stream'` to pipe the file download from your custom API directly to the user's browser. If your API returns the file bytes using a simple HTTP response without proper chunking and Content-Length headers, the Axios stream will fail to pipe efficiently.

**The Fix:** If using FastAPI, do not manually chunk bytes or return static `Response` objects. Extract your file to a temporary disk location and return it using a native `FileResponse`. This guarantees perfect HTTP/1.1 stream headers (Content-Length, Accept-Ranges) that Axios requires.

```python
from fastapi.responses import FileResponse
import os

@app.get("/download/{session_id}/{filename}")
async def download_file(session_id: str, filename: str):
    # Extract from docker, save to /tmp
    tmp_path = f"/tmp/{session_id}_{filename}"
    # ... extraction logic ...
    
    # Let FastAPI handle all the complex streaming headers automatically
    return FileResponse(path=tmp_path, filename=filename)
```

### Issue B: Blob URL Race Condition (Frontend)
LibreChat's React frontend receives the file stream as a `Blob`, generates a temporary `blob:http://` URL, assigns it to a hidden `<a>` tag, clicks it, and then instantly revokes the URL.

```javascript
// Inside LibreChat's LogLink.tsx / Citation.tsx
link.href = stream.data; // e.g. blob:http://localhost:3080/41db7091-3d22...
link.click();
window.URL.revokeObjectURL(stream.data); // The bug!
```

**The Bug:** In certain browsers (especially Chrome), the synchronous `revokeObjectURL` call destroys the memory pointer *before* the browser's download manager can pull the file bytes. The browser aborts the download, throws an internal "Not Found" error (which LibreChat reads as a Network Error), and falls back to using the last segment of the destroyed URL (the UUID `41db7091...`) as the filename.

**The Fix:** You must patch your LibreChat instance's frontend code to delay the revocation. If you are using standard `docker-compose.yml`, you can patch the compiled JS inside the running container using `sed` or Python:

```bash
docker exec librechat python3 -c "import re; f='/app/client/dist/assets/index.js'; text=open(f).read(); new_text=re.sub(r'window\.URL\.revokeObjectURL\(([^)]+)\)', r'setTimeout(()=>window.URL.revokeObjectURL(\1),3000)', text); open(f,'w').write(new_text)"
```
*(Note: Replace `index.js` with the actual hashed filename in your `/app/client/dist/assets/` directory).*

By using `FileResponse` on your API backend and patching the `revokeObjectURL` race condition on the LibreChat frontend, file downloads will work flawlessly across all browsers.
