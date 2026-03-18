# Non-Existent Tools Analysis

Analysis of calls to tools/commands that don't exist or aren't available in the environment.

---

## Problem Statement

From the deep analysis, we identified errors related to calling:
1. **Claude tools/skills that don't exist** (e.g., "Unknown skill: journal-search")
2. **Unix/Linux commands on Windows** (e.g., pkill, grep, sed on Windows without WSL)
3. **Missing system commands** (e.g., exit code 127 errors - "command not found")
4. **Deprecated tool names** (e.g., old skill names that have been renamed)

These errors are 100% preventable with upfront validation.

---

## Categories of Non-Existent Tools

### 1. Unknown Skills/Nested Tools (Critical)

**Examples:**
- `skill: "superpowers:brainstorm"` (deprecated - should be `superpowers:brainstorming`)
- `skill: "journal-search"` (misspelled or invalid)
- Tools that are gated/unavailable in current environment

**Error Pattern:**
```
<tool_use_error>Unknown skill: journal-search</tool_use_error>
```

**Root Cause:**
- Typo in skill name
- Skill was renamed/deprecated
- Skill not available in current environment
- Skill requires specific authorization

**How to Prevent:**
- List available skills first: `shortcuts_list` tool
- Verify skill name matches exactly
- Check if skill is gated (requires permission/auth)
- Don't assume skill exists - verify first

---

### 2. Unix/Linux Commands on Windows

**Examples:**
- `pkill` — kill process by name (Unix only, no Windows equivalent)
- `grep` — should use `Grep` tool or `findstr` on Windows
- `sed` — stream editor (Unix only)
- `awk` — text processing (Unix only)
- `ls -la` — should use `Glob` or `Get-ChildItem` on Windows
- `which` — which command (Windows: `where`)
- `chmod` — change permissions (doesn't exist on Windows)

**Error Pattern:**
```
Exit code 127
/bin/bash: pkill: command not found
```

**Root Cause:**
- Command is Unix-specific
- Windows doesn't have equivalent in PATH
- WSL not available or not in use
- Assuming POSIX compatibility

**How to Prevent:**
- Know your environment: Windows vs Linux/Mac
- For `pkill` → no direct Windows equivalent (use Task Manager or PowerShell)
- For file operations → use Glob/Grep/Read tools instead
- For text processing → use dedicated tools, not sed/awk
- Test commands locally first

---

### 3. Missing System Commands

**Examples:**
- `python3` — should check for `python` or `python3.11` specifically
- `node` — should verify Node.js installed with correct version
- `git` — should verify Git is in PATH
- `docker` — should verify Docker daemon is running
- Custom scripts — should use full path, not rely on PATH

**Error Pattern:**
```
Exit code 127
command not found: python3

OR

Exit code 127: /usr/bin/bash: line 1: node: command not found
```

**Root Cause:**
- Command not in PATH
- Command installed in non-standard location
- Command not installed at all
- Wrong command name/version

**How to Prevent:**
- Use `which python3` or `command -v python3` to verify before using
- Use full paths if command might not be in PATH
- Check environment: `echo $PATH`
- Verify tool is installed: test with simple command
- For cross-platform: use `python` not `python3`, or handle both

---

### 4. Deprecated Tool Names

**Examples (from analysis):**
- `superpowers:brainstorm` → renamed to `superpowers:brainstorming`
- `superpowers:write-plan` → renamed to `superpowers:writing-plans`
- `superpowers:execute-plan` → renamed to `superpowers:executing-plans`

**Error Pattern:**
```
Unknown skill: brainstorm
```

**Root Cause:**
- Skill API changed
- Skill was renamed
- Using old documentation or memory

**How to Prevent:**
- Always check current skill names
- Reference official skill list from `shortcuts_list`
- Don't rely on old documentation
- When a skill fails as "Unknown", it's been renamed

---

## Detection Patterns from Analysis

### Common Error Types Found:
- "Unknown skill" errors (e.g., journal-search)
- Exit code 127 (command not found) errors
- `pkill` attempts on Windows systems
- `grep` used instead of `Grep` tool
- `sed` / `awk` attempts

### Most Common Windows-Specific Issues:
1. Using Unix command names
2. Assuming POSIX tools available
3. Not checking command availability
4. Assuming PATH includes all commands

---

## Recommended Guidelines for CLAUDE.md

### Guideline: Verify Tool Existence Before Calling

```yaml
verify-tool-existence-before-calling: |
  Before calling ANY tool (skill, command, or native tool):

  For Claude Skills/Tools:
  - Use shortcuts_list tool first to see available skills
  - Verify exact spelling (brainstorming not brainstorm)
  - Check if skill requires special permissions/environment
  - Don't assume skill exists - always list first

  For Bash Commands:
  - Use `command -v CMD` to verify command exists
  - Use `which CMD` to check if in PATH
  - For cross-platform: test on actual system first
  - Remember Windows doesn't have: pkill, grep, sed, awk, chmod, etc.

  For System Tools:
  - Python: test with `python --version` before using
  - Node: test with `node --version` before using
  - Git: test with `git --version` before using
  - Scripts: use full paths from pwd or known directories

  This prevents "command not found" and "Unknown skill" errors.
```

---

## Windows vs Unix Command Mapping

When you think of a Unix command, here's what to do on Windows:

| Unix Command | Windows Option | Better Solution |
|--------------|----------------|-----------------|
| `ls` | `dir` or `Get-ChildItem` | Use **Glob** tool |
| `grep` | `findstr` or `Select-String` | Use **Grep** tool |
| `cat` / `head` / `tail` | `type` or `Get-Content` | Use **Read** tool |
| `find` | `dir /s` or `Get-ChildItem -r` | Use **Glob** tool |
| `sed` | `(Get-Content) -replace` | Use **Edit** tool |
| `awk` | PowerShell script | Use **Grep** with regex |
| `pkill` | `taskkill /IM name.exe` | No Claude equivalent - ask user |
| `which` | `where` | Test with `command -v` |
| `chmod` | `icacls` (different permissions model) | Not applicable in Claude |
| `sudo` | Run as admin or `Invoke-Command` | Not applicable in Claude |

**Bottom line:** Use Claude's dedicated tools (Glob, Grep, Read, Edit) instead of trying to run Unix commands.

---

## Deprecated Skill Names (Reference)

Update any of these if you see them fail:

| Old Name | New Name | Status |
|----------|----------|--------|
| `superpowers:brainstorm` | `superpowers:brainstorming` | Renamed |
| `superpowers:write-plan` | `superpowers:writing-plans` | Renamed |
| `superpowers:execute-plan` | `superpowers:executing-plans` | Renamed |

If a skill returns "Unknown skill", check the new name in available skills list.

---

## Practical Prevention Checklist

When about to call a tool:

- [ ] **For Claude Skills:** Did I run `shortcuts_list` first?
- [ ] **For Bash:** Did I test this command on my system first?
- [ ] **For Bash:** Is this a Unix-only command? (on Windows?)
- [ ] **For Bash:** Does the command exist in PATH? (use `command -v`)
- [ ] **For Tools:** Am I using the right tool name (no typos)?
- [ ] **For Scripts:** Am I using the full path?
- [ ] **For Tools:** Is the tool available in my environment?
- [ ] **For Tools:** Do I have permissions to use this tool?

---

## Error Recovery

If you get "command not found" or "Unknown skill":

1. **Stop immediately** — don't retry the same command
2. **Verify existence** — use `command -v` for bash, `shortcuts_list` for skills
3. **Use alternative** — switch to dedicated Claude tool or different approach
4. **Ask if unclear** — if there's no equivalent, ask user for guidance

---

## Common Mistakes (From Analysis)

### Wrong Approach
```bash
# Trying to use Unix commands on Windows
pkill python  # ← Won't work on Windows!
grep "text" file.txt  # ← Use Grep tool instead!
sed 's/old/new/' file.txt  # ← Use Edit tool instead!
ls -la /some/path  # ← Use Glob tool instead!
```

### Right Approach
```bash
# Use dedicated tools
Grep tool: search for "text" in file.txt
Glob tool: find /some/path
Edit tool: replace old with new in file
Read tool: view /some/path directory

# Or use Windows equivalents for bash:
Get-ChildItem -Path /some/path  # PowerShell instead of ls
```

---

## Summary

**Non-existent tool calls are 100% preventable:**

1. **For Claude Skills:** Use `shortcuts_list` before calling
2. **For Bash:** Use `command -v` to verify command exists
3. **For Unix on Windows:** Use dedicated Claude tools instead
4. **For Deprecated Skills:** Check new names in skill list

**Implementation Priority:** HIGH
- Easy to implement
- Very few false positives
- Prevents wasted context tokens
- Eliminates confusing error messages

---

## Suggested CLAUDE.md Entry

### Verify Tool/Command Existence Before Calling

**Rule**: Always verify tools and commands exist before calling them

**Why**: Calling non-existent tools is a preventable error source — includes pkill on Windows, unknown skills, missing commands

**How to apply**:
- For Claude Skills: Use `shortcuts_list` tool first to see available skills
- For Bash commands: Use `command -v CMD` to verify command in PATH before using
- Don't call Unix-only commands on Windows: pkill, grep, sed, awk, chmod don't exist
- Don't use deprecated skill names: brainstorm → brainstorming, write-plan → writing-plans
- For missing commands: test with `CMD --version` first

**Common Windows issues to avoid**:
- `pkill` - no Windows equivalent, use PowerShell taskkill instead
- `grep` - use Grep tool or findstr on Windows
- `sed` - use Edit tool instead
- `awk` - use Grep tool with regex instead
- `chmod` - not applicable on Windows (different permissions model)

**Prevents**: "command not found" and "unknown skill" errors

---

## See Also

- Exit code 127 in tool_failures analysis
- "Unknown skill" error pattern analysis
- Bash command availability analysis
