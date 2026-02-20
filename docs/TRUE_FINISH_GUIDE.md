# LibreChat Code Interpreter: "True Finish" Integration Guide

This document explains how to resolve the final UI-layer issues (404 errors and missing file icons) to ensure a production-ready setup for your Code Interpreter.

## 1. Fix the 404 Download Error
When the LLM generates a link like `/run/download/...`, the browser looks for it on port `3080`. You need to ensure these requests reach the backend API on port `8000`.

### Option A: Reverse Proxy (Recommended)
Add this location block to your Nginx configuration. This allows relative Markdown links from the LLM to work perfectly.
```nginx
location /run/download/ {
    proxy_pass http://librechat_code_interpreter_api:8000/run/download/;
    proxy_set_header Host $host;
}
```

### Option B: Absolute URL Prompting
Add this to your Agent's System Prompt:
> "Always provide download links as absolute URLs: `http://localhost:8000/run/download/{session_id}/{filename}`"

---

## 2. Advanced: Native UI Integration (File Attachments)

To make files appear as clickable attachment icons in the chat UI without the LLM needing to generate a link:

1. **Storage Environment**: Add these to your `librechat` service in `docker-compose.full.yml`:
   ```yaml
   environment:
     - STORAGE_TYPE=local
     - FILES_DIR=/app/api/data/files
     - IMAGES_DIR=/app/api/data/images
   ```
2. **API Response format**: Ensure your Code Interpreter API returns a structured `files` array. While our current API returns a list of strings (`["file.txt"]`), high-end integrations often return objects like `[{"filename": "...", "url": "..."}]`. 

---

## 3. Best Practices
- **Use High-Performance Models**: `Qwen3-Coder-30B` is essential for reliable link formatting and complex code logic.
- **Cleanup & Security**: The API handles idle cleanup (`RCE_SESSION_TTL`) and auth (`X-API-Key`). For browser downloads, use the `?api_key=...` query parameter (PR #27).
