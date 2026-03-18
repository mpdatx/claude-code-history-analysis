# CLAUDE.md Guidelines

14 evidence-based directives for reducing tool errors in Claude Code sessions. Each addresses a specific failure pattern found in session history analysis.

---

## 1. Edit: Always Read First [CRITICAL]

**Rule**: Use Read tool before Edit — verify exact file content and indentation.

**Why**: "File not read yet" and "string to replace not found" are the most common Edit failures. Indentation mismatches are the #1 cause.

**How to apply**:
- When editing files ALWAYS use Read first to verify content exists and see exact formatting
- Copy old_string character-for-character from Read output (tabs/spaces matter!)
- Verify old_string is unique in file or use replace_all: true
- Check indentation carefully — must match exactly (tabs vs spaces)
- If Edit fails with "string to replace not found", indentation is usually wrong

---

## 2. Bash: Break Complex Commands + Error Checking [CRITICAL]

**Rule**: Break bash commands into multiple smaller commands, each with error checking.

**Why**: Exit code 1 and exit code 127 are the most common errors — indicates unhandled failures in complex pipelines.

**How to apply**:
- For Bash commands with pipes or multiple operations, break into separate commands
- Use `set -e` at start of scripts to exit on first error, OR add `|| exit 1` after each operation
- Test each step independently first
- Never pipe more than 2 commands without intermediate verification
- For exit code 127 (command not found): verify command exists with `command -v CMD`

---

## 3. Use Dedicated Tools, Not Bash [CRITICAL]

**Rule**: Use dedicated tools instead of Bash for file operations.

**Why**: Glob, Grep, and Read tools provide better error messages, consistent output, and proper permission handling.

**How to apply**:
- NEVER use Bash `ls` → use **Glob** tool instead
- NEVER use Bash `grep` or `rg` → use **Grep** tool instead
- NEVER use Bash `cat`, `head`, `tail` → use **Read** tool instead
- NEVER use Bash `find` → use **Glob** tool instead

---

## 4. Settings.json: Add Permission Allowlist [HIGH]

**Rule**: Add commonly-needed tools to settings.json permissions.

**Why**: Read, Bash, and Agent are frequently blocked — creates friction and permission request dialogs.

**How to apply**:
```json
{
  "permissions": {
    "allow": ["Read", "Bash", "Agent", "Edit", "Write"]
  }
}
```

For projects with specific tool restrictions, use per-project settings.json overrides instead of global allowlist.

---

## 5. Verify Tool/Command Existence Before Calling [CRITICAL]

**Rule**: Always verify tools and commands exist before calling them.

**Why**: Calling non-existent tools is a common error source — includes pkill on Windows, unknown skills, missing commands.

**How to apply**:
- For Claude Skills: Use `shortcuts_list` tool first to see available skills
- For Bash commands: Use `command -v CMD` to verify command in PATH
- Don't call Unix-only commands on Windows: pkill, grep, sed, awk, chmod
- Don't use deprecated skill names: check skill list first
- For missing commands: test with `CMD --version` before using

**Common Windows issues to avoid**:
- `pkill` → use `taskkill /IM processname.exe`
- `grep` → use Grep tool or `findstr`
- `sed` → use Edit tool
- `awk` → use Grep tool with regex
- `ls` → use Glob tool
- `chmod` → not applicable on Windows

---

## 6. Bash: Avoid Compound Commands [HIGH]

**Rule**: Don't use compound commands (`cd dir && git status`). Use single commands or split into separate operations.

**Why**: Compound commands cause permission prompt fatigue and obscure failures.

**How to apply**:
- `cd DIR && git status` → `git -C DIR status`
- `cd DIR && npm test` → `npm --prefix DIR test`
- `cd DIR && python script.py` → `python DIR/script.py`
- `cd DIR && ls` → use **Glob** tool: `Glob(pattern: "DIR/*")`
- For multi-step workflows: call Bash separately for each step with explicit error handling between steps

---

## 7. Bash: PATH Verification [HIGH]

**Rule**: Verify command availability and PATH before running.

**Why**: Exit code 127 (command not found) is common with Python, Node, and package managers.

**How to apply**:
- **Linux/Mac/WSL**: `command -v python` or `which python`
- **Windows (Git Bash)**: `where python` or `command -v python`
- **Windows (CMD)**: `where python`
- For Python: use `python` not `python3` (more portable on Windows)
- For custom scripts: always use absolute paths
- Never assume Unix commands exist on Windows

---

## 8. Read: Handle Large Files [HIGH]

**Rule**: Use limit/offset parameters for large files; read in sections.

**Why**: Token limit errors prevent reading large files; need segmented approach.

**How to apply**:
- For files larger than ~20KB, use limit and offset parameters
- Start with first 100 lines: `limit: 100, offset: 0`
- If file is known to be large, always use limit
- Token limit errors indicate file is too large — reduce limit further
- Use Grep to search for specific patterns instead of reading whole file

---

## 9. Read Tool: Use Numeric limit/offset Parameters [HIGH]

**Rule**: When using Read tool's limit and offset parameters, they MUST be numbers, not strings.

**Why**: InputValidationError occurs when offset/limit passed as strings instead of numbers.

**How to apply**:
- Always use `limit: 100` (not `limit: "100"`)
- Always use `offset: 0` (not `offset: "0"`)
- String values for file_path are OK: `file_path: "/path/to/file.txt"`

---

## 10. Check Service State Before Managing [HIGH]

**Rule**: Query current state before starting, stopping, killing, or restarting services/processes.

**Why**: Without state awareness, Claude wastes time starting already-running services or killing non-existent processes.

**How to apply**:
- **Before starting**: Check if already running
  - **Linux/Mac**: `pgrep SERVICE_NAME` or `lsof -i :PORT`
  - **Windows**: `netstat -ano | findstr :PORT` or `tasklist | findstr SERVICE_NAME`
- **Before stopping/killing**: Verify process exists first
- **Before restarting**: Ask user if they started it manually
- If a service fails to start, diagnose why before retrying (port in use? permissions?)
- Never use `pkill` on Windows — use `taskkill /IM processname.exe`

**When to defer to user**: manual start, custom parameters, managed by systemd/docker, or uncertain state.

---

## 11. Parameter Validation Before Tool Calls [MEDIUM]

**Rule**: Verify tool parameters before calling.

**Why**: InputValidationError indicates incorrect parameter types/formats.

**How to apply**:
- File paths: must be absolute, not relative
- Edit tool: old_string must be character-for-character exact match
- Bash: command must be valid shell syntax
- Read: file must exist — use Glob to verify before Reading
- All paths: use proper path format for the platform

---

## 12. File Editing Workflow [MEDIUM]

**Rule**: Follow this sequence when editing files.

**Why**: "File not read yet" is the #1 Edit error — prevents procedural mistakes.

**How to apply**:
1. Use Read tool first — verify file exists and see exact content
2. Copy old_string exactly from Read output (character-for-character)
3. Verify old_string is unique in file or use replace_all: true
4. Check indentation carefully — must match exactly
5. Then call Edit with verified parameters

Never skip step 1.

---

## 13. Permission Checking Before Operations [MEDIUM]

**Rule**: Check permissions before attempting file operations.

**Why**: Permission errors block file operations and tool execution.

**How to apply**:
- Before file operations: check file exists with Glob first
- Check directory write permissions for Create/Write/Edit operations
- Verify tool permissions in settings.json
- Use per-project settings.json for scoped tool restrictions

---

## 14. Error Recovery: Diagnosis Before Retrying [MEDIUM]

**Rule**: When a tool fails, diagnose before retrying.

**Why**: Repeated retries without understanding failure wastes context.

**How to apply**:
1. Stop immediately — don't retry the same command
2. Read the full error message — identify the category
3. Diagnose root cause: syntax error? wrong parameters? missing file?
4. Fix the root cause
5. Retry once with the fix
6. If still fails after one retry, try a different approach

Never retry the same failing command 3+ times without changes.
