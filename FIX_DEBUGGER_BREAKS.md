# Fix VS Code Debugger Breaking on Caught Exceptions

## Issue
VS Code debugger is breaking at line 369 in `duckdb_backend.py` on the BinderException, even though our code properly catches and handles this exception.

## Root Cause  
The VS Code Python debugger is configured to break on **all exceptions**, including **caught exceptions**. This is why it stops at the line where the exception is raised, before our exception handler can process it.

## Solution

### Option 1: Configure VS Code Debugger Exception Settings
1. **Open VS Code debugger**
2. **In the Call Stack panel**, look for exception settings
3. **Uncheck "Caught Exceptions"** or specifically **uncheck "BinderException"**
4. **Keep "Uncaught Exceptions" checked** (this is what you want to catch)

### Option 2: Add .vscode/launch.json Configuration
Create/modify `.vscode/launch.json` with proper exception handling:

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: Current File",
            "type": "python",
            "request": "launch",
            "program": "${file}",
            "console": "integratedTerminal",
            "justMyCode": true,
            "exceptionHandling": {
                "breakOnUncaughtExceptions": true,
                "breakOnCaughtExceptions": false
            }
        }
    ]
}
```

### Option 3: Temporary Debug Workaround
If you need to debug but want to skip the BinderException, add this temporary code:

```python
# Temporary debug bypass - remove after debugging
import os
if os.getenv('MPZSQL_DEBUG_SKIP_BINDER_CHECK'):
    # Skip PREPARE check in debug mode
    return pa.schema([])
```

Then set environment variable: `export MPZSQL_DEBUG_SKIP_BINDER_CHECK=1`

## Verification
Our code **is working correctly**. The test shows:
- BinderException is properly caught ✅
- Empty schema is returned as expected ✅  
- Server doesn't crash ✅

## Summary
This is a **debugger configuration issue**, not a code issue. The exception handling is working perfectly - the debugger is just configured to break on all exceptions instead of only uncaught ones.