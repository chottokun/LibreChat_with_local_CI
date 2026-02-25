# Bug Report: LibreChat Code Interpreter Session ID Omission

## 1. Description

There is a critical design flaw in the official LibreChat `@librechat/agents` package that causes the `session_id` to be omitted from the request payload during certain code execution flows.

When a user initiates code execution **without attaching any files**, the client-side tool logic fails to include the top-level `session_id` property in the POST request to the `/exec` endpoint.

## 2. Impact

This omission causes the Code Interpreter API to:
1.  Assume every request is from a brand-new, independent session.
2.  Spin up a completely fresh Docker container for every single message.
3.  **Performance Degresson**: Launches can take 2-3 seconds, leading to a "heavy" or "slow" user experience.
4.  **State Loss**: Variables or files created in one turn are not persisted to the next turn, as the container is different each time.

## 3. Root Cause Analysis

Analysis of `@librechat/agents/src/tools/CodeExecutor.ts`:

```typescript
// Line 124 in @librechat/agents (v0.8.3-rc1)
const postData: Record<string, unknown> = {
  lang,
  code,
  ...rest,
  ...params,
};

// ... session_id is extracted but only used for file lookups
const { session_id, _injected_files } = (config.toolCall ?? {}) as {
  session_id?: string;
  _injected_files?: t.CodeEnvFile[];
};

// ... session_id is NEVER added to postData at the root level!
```

The code fails to perform `postData.session_id = session_id;`.

## 4. Implemented Fix (Workaround)

Since the client-side bug is in an external dependency, the Code Interpreter API (`main.py`) has been updated with a robust fallback mechanism.

### `main.py`
```python
# Fallback to user_id to ensure container reuse and improve performance
if not effective_session_id and req.user_id:
    effective_session_id = f"user_{req.user_id}"
```

By using the `user_id` as the session key when the official `session_id` is missing, we ensure that:
-   Containers are reused per user.
-   Latency is reduced from seconds to milliseconds.
-   State persists correctly within a user's context.

## 5. References
- [Issue location in @librechat/agents](https://github.com/danny-avila/LibreChat/blob/main/packages/agents/src/tools/CodeExecutor.ts)
- [Project Documentation](file:///home/nobuhiko/Project/LibreChat_with_local_CI/docs/librechat_integration_guide.md)
