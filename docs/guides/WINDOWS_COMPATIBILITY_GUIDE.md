# Windows Compatibility Guide for CLAUDE.md Guidelines

When using Claude Code on Windows, several guidelines need Windows-specific commands and considerations.

---

## Summary: Which Guidelines Need Attention on Windows

| Guideline | Windows Compatible? | Issue | Solution |
|-----------|-------------------|-------|----------|
| 1. Edit - Always Read First | ✅ Yes | None | Works as-is |
| 2. Bash - Error Checking | ⚠️ Partial | Different exit code syntax | Use `%ERRORLEVEL%` in cmd.exe |
| 3. Use Dedicated Tools | ✅ Yes | None | Preferred approach on Windows |
| 4. Settings.json Permissions | ✅ Yes | None | Works as-is |
| 5. Verify Tool Existence | ✅ Yes | Already Windows-aware | Uses `where` instead of `which` |
| 6. Bash - Error Checking Pattern | ⚠️ Partial | Syntax differs | Documented in guideline |
| 7. Bash - PATH Verification | ⚠️ Partial | Different verification commands | Use `where` or `%PATH%` |
| 8. Read - Handle Large Files | ✅ Yes | None | Works as-is |
| 9. Read Tool - Numeric Parameters | ✅ Yes | None | Works as-is |
| **10. Service State Before Managing** | ⚠️ Partial | Different process/port checking | Use `tasklist`, `netstat`, `taskkill` |
| 11. Parameter Validation | ✅ Yes | Forward slashes OK in paths | Works as-is |
| 12. File Editing Workflow | ✅ Yes | None | Works as-is |
| 13. Permission Checking | ✅ Yes | Different permissions model | Use `icacls` instead of `chmod` |
| 14. Error Recovery | ✅ Yes | None | Works as-is |

---

## Commands That DON'T Work on Windows

These Unix/Linux commands have no Windows equivalent and should never be used:

| Command | What it does | Windows Alternative | Better Solution |
|---------|-------------|-------------------|-----------------|
| `pkill` | Kill process by name | `taskkill /IM name.exe` | **Don't manage services - ask user** |
| `grep` | Text search in files | `findstr` or `Select-String` | **Use Grep tool instead** |
| `sed` | Stream text editor | `(Get-Content) \| %{$_ -replace}` | **Use Edit tool instead** |
| `awk` | Text processing | PowerShell equivalent | **Use Grep tool with regex** |
| `ls -la` | List files | `dir` or `Get-ChildItem` | **Use Glob tool instead** |
| `find` | Find files | `dir /s` or `Get-ChildItem -r` | **Use Glob tool instead** |
| `cat` | Display file | `type` or `Get-Content` | **Use Read tool instead** |
| `chmod` | Change permissions | `icacls` | Not applicable (different model) |
| `which` | Find command | `where` | **Use `where CMD` on Windows** |
| `lsof -i :PORT` | Check port usage | `netstat -ano \| findstr :PORT` | See service state guideline |

---

## Platform-Specific Bash Syntax

### Checking Exit Codes

**Linux/Mac/Bash:**
```bash
command_that_might_fail || exit 1
if [ $? -ne 0 ]; then echo "Failed"; fi
set -e  # Exit on error
```

**Windows (Git Bash/WSL/Bash for Windows):**
```bash
# Same as Linux/Mac - bash syntax works
command_that_might_fail || exit 1
if [ $? -ne 0 ]; then echo "Failed"; fi
```

**Windows (cmd.exe only):**
```cmd
command_that_might_fail
if %ERRORLEVEL% neq 0 (
  echo Failed
  exit /b 1
)
```

**⚠️ Important:** If you use Bash/Git Bash on Windows, use bash syntax. Only use cmd.exe syntax if explicitly required.

---

## Verifying Commands Exist on Windows

### Method 1: `where` (works everywhere on Windows)
```bash
where python          # Finds python in PATH
where node            # Finds node.js
where git             # Finds git
```

### Method 2: Version check (works on both platforms)
```bash
python --version
node --version
git --version
npm --version
```

### Method 3: Test import (for languages)
```bash
python -c "import sys; print(sys.version)"  # Verify Python
node -e "console.log(process.version)"      # Verify Node
```

### Method 4: PowerShell (if on Windows)
```powershell
Get-Command python  # Find if command exists
$env:PATH          # Show PATH variable
```

---

## Checking Port Usage (Service State Guideline)

### Linux/Mac:
```bash
lsof -i :8080          # Check if port 8080 is in use
ps aux | grep SERVICE  # Find process by name
```

### Windows:
```bash
# Git Bash/WSL (can use Linux commands if available)
netstat -ano | findstr :8080    # Check port 8080

# cmd.exe
netstat -ano | findstr :8080
tasklist | findstr SERVICE_NAME  # Find process by name
```

### Best Practice: Query Windows via Bash
```bash
# Works on Windows (Git Bash/WSL/Bash for Windows)
netstat -ano | findstr :8080          # Port check
tasklist | findstr processname        # Process check
```

---

## Killing Processes on Windows

### ⚠️ CRITICAL: Always Ask User First

**DO NOT use `pkill` on Windows** - it doesn't exist.

If user explicitly asks to stop a service:

**Option 1: taskkill (cmd.exe syntax)**
```bash
taskkill /IM processname.exe /F
```

**Option 2: Stop service (if it's a Windows service)**
```bash
net stop ServiceName
sc stop ServiceName
```

**Better Option: Let user do it**
- User manually started the service → user should stop it
- Service is in development → ask user to stop it
- Reduces conflicts and surprises

---

## Path Handling on Windows

### Forward vs Backslash
- ✅ Forward slashes work in most tools: `/path/to/file`
- ✅ Windows paths in Claude tools: `C:/Users/name/file.txt`
- ❌ Avoid backslashes in parameters: Don't use `C:\Users\name\file.txt`
- ✅ Bash environment: Forward slashes work: `/c/Users/name/file.txt`

### Examples
```bash
# ✅ DO THIS (works everywhere)
Read(file_path: "C:/Users/myname/file.txt")
Glob(pattern: "src/**/*.ts")

# ❌ DON'T DO THIS (backslashes cause issues)
Read(file_path: "C:\Users\myname\file.txt")
```

---

## Environment Variables on Windows

### Check PATH
```bash
# Bash / Git Bash / WSL
echo $PATH

# cmd.exe
echo %PATH%

# PowerShell
$env:PATH
```

### Set Environment Variables (Bash/Git Bash)
```bash
export PYTHON_PATH=/c/Python39
export NODE_PATH=/c/Program\ Files/nodejs
```

### Set Environment Variables (cmd.exe)
```cmd
set PYTHON_PATH=C:\Python39
set NODE_PATH=C:\Program Files\nodejs
```

---

## Windows-Specific Tool Tips

### When Using Bash on Windows
- **Git Bash**: `/c/Users/...` for Windows paths
- **WSL**: `/mnt/c/Users/...` for Windows paths
- **Built-in Bash (Windows 10+)**: `/mnt/c/Users/...`

### Recommended Approach on Windows
1. **Use dedicated Claude tools** (Glob, Grep, Read, Edit) - platform independent
2. **Use Bash when needed** - Git Bash or WSL provides Unix commands
3. **Avoid mixing** cmd.exe and bash syntax
4. **Ask user for system-level operations** - killing processes, starting services, etc.

---

## Windows PATH Issues

Common reason for "command not found" on Windows:

### Issue: Python not found
```bash
# ❌ WRONG - will fail if python3 not in PATH
python3 --version

# ✅ RIGHT - more portable
python --version
where python  # Check if available first
```

### Issue: Node not found
```bash
# ❌ Might fail if installed in non-standard location
node --version

# ✅ Check first
where node
node --version
```

### Issue: npm not in PATH
```bash
# ❌ Might not be in PATH even if Node is installed
npm install

# ✅ Better
where npm
npm install
```

---

## Quick Checklist for Windows

Before running any Bash command on Windows:

- [ ] Does this command exist on Windows? (ps, grep, sed, awk, pkill, chmod, lsof, etc.)
- [ ] Is there a Windows equivalent I should use instead? (`where`, `tasklist`, `netstat`)
- [ ] Is there a Claude dedicated tool instead? (Glob, Grep, Read, Edit)
- [ ] Does the command assume Unix paths? (`/usr/bin`, `/home`, etc.)
- [ ] Does the command reference Unix-only features? (file permissions, process signals)
- [ ] Should I ask the user to do this manually instead?

---

## Summary

**The Golden Rule for Windows: Use dedicated Claude tools when available, ask user for system-level operations.**

This avoids platform-specific issues and keeps interactions simple and safe.
