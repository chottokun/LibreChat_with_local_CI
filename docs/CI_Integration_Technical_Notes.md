# Walkthrough - LibreChat Integration Debugging

I have identified and addressed several critical issues regarding file handling in the Code Interpreter integration.

## Issues Resolved

### 1. Upload Validation (422 Error)
LibreChat sometimes sends the file in a field named `file` instead of `files`, and may not provide `entity_id` during the initial upload. I updated the `/upload` endpoint to handle these variations gracefully.

### 2. Volume Path Mismatch & Execution Path (/mnt/data)
The `RCE_DATA_DIR` was being confused between host-local and container-bound paths. I separated them into `RCE_DATA_DIR_HOST` and `RCE_DATA_DIR_INTERNAL` to ensure Docker volume mounts work correctly.
**Crucially, LibreChat agents expect files to be located at `/mnt/data/` within the sandbox.** Previously, the API was hardcoded to `/usr/src/app`. I updated the backend configurations and working directories to align precisely with the `/mnt/data/` path standard expected by Gemini and LibreChat prompts.

### 3. Agent Builder Compatibility (500 Error)
When using the 'Agent Builder' upload function, LibreChat expects the API's `/files` endpoint to return a JSON array strictly containing file objects. The API was previously returning a nested dictionary (`{"files": [...]}`), causing a `response.data.find is not a function` error in the UI. I corrected the JSON structure.

### 5. Session Management & Empty Sandboxes
LibreChat sends the `session_id` inside the `files` array payload for its `/exec` endpoint rather than at the root level. Previously, the API expected it at the root (`req.session_id`), and finding it `None`, generated a new (empty) session container for every execution. I updated the API to scan the `files` array to match the execution session ID with the upload session ID.

### 6. File Download Errors (404)
Even though files were generated and uploaded correctly, clicking the UI file chip resulted in a 404 error. The API's `/download` endpoint was attempting to resolve the file path using `RCE_DATA_DIR` (`/mnt/data` inside the sandbox) instead of `RCE_DATA_DIR_INTERNAL` (`/app/shared_volumes/sessions/` on the API container). I fixed the path resolution logic to correctly serve the file from the API's internal volume mapping.


## Verification Evidence

### PDF Upload Test
I verified that PDF files can be uploaded and processed without the red error message.
![PDF Upload Success](/home/nobuhiko/.gemini/antigravity/brain/b347543b-8340-4308-930f-61a22e510652/librechat_ci_agent_pdf_test_1771668899648.webp)

### Full Cycle (Upload -> Run -> Download)
The following recording shows a successful full cycle where a file is uploaded, used in code execution, and a result is downloaded.
![Full Cycle Test](/home/nobuhiko/.gemini/antigravity/brain/b347543b-8340-4308-930f-61a22e510652/librechat_full_cycle_test_v2_1771663336267.webp)

## Conclusion
The backend is now highly resilient to different upload patterns. If errors persist, please try clearing the browser cache or starting a fresh chat session to reset the UI state.
