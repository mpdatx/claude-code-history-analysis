# Daily Failure Reports

Generates daily reports of failed tool calls, organized by project and time.

---

## What It Does

Creates one markdown report file per day containing:
- **Summary statistics** (total failures, affected projects/tools, error types)
- **Failures grouped by project** (first level of organization)
- **Failures ordered by time** (within each project, chronological order)
- **Error samples** (showing first 5 errors per project with full context)

---

## Usage

### Generate reports for all dates
```bash
python tools/cli.py daily --date all
```

### Generate report for specific date
```bash
python tools/cli.py daily --date YYYY-MM-DD
```

### Generate report for most recent day (default)
```bash
python tools/cli.py daily
```

### Custom output directory
```bash
python tools/cli.py daily --date all --output-dir ./my_reports
```

### Scoped to specific projects
```bash
python tools/cli.py daily --projects-dir "%USERPROFILE%\.claude\projects\G--*"
```

Alternative module invocation:
```bash
python -m claude_history daily
```

---

## Report Structure

Each daily report (`failures_YYYY-MM-DD.md`) contains:

```
# Failed Tool Calls — YYYY-MM-DD

## Summary
- Total Failures: N
- Affected Projects: N
- Affected Tools: N

### By Tool
- Bash: N
- Edit: N
- Read: N
[etc.]

### By Error Type
- Exit Code: N
- Other: N
- Validation: N
[etc.]

## Failures by Project

### project-name-1
**Total**: N failures

| Time | Tool | Error Type | Session |
|------|------|-----------|---------|
| 03:24:15 | Bash | exit_code | session-id |
| 03:24:37 | Edit | other | session-id |
[chronological order]

**Error Samples**:
[First 5 errors with full stack traces]

---

### project-name-2
[Same structure...]
```

---

## Key Features

- **One file per day** - Easy to find reports for specific dates
- **Organized by project first** - See which projects had issues
- **Then chronological within project** - Understand incident timeline
- **Summary statistics** - Quick overview of failure patterns
- **Error samples** - See actual error messages
- **Error classification** - Exit code, validation, timeout, etc.

---

## Examples

### View today's failures
```bash
python tools/cli.py daily
```

### Find worst day by file size
```bash
python tools/cli.py daily --date all
```

### Search for specific error across days
Use the Grep tool to search for patterns across daily report files.

### Get timeline of specific project
```bash
python tools/cli.py timeline
```

---

## Options

```
--projects-dir PATH      Claude projects directory (default: auto-detect)
--output-dir PATH        Where to save reports (default: ./daily_failure_reports)
--date YYYY-MM-DD        Specific date, or 'all' for all dates
--help                   Show help
```

---

## Implementation Notes

- Auto-detects Claude projects directory (`~/.claude/projects/`)
- Handles large histories efficiently (streaming JSON parsing)
- Creates output directory if it doesn't exist
- One file per day - easy to version control or archive
- Error samples limited to first 5 per project (to keep file size reasonable)
- Error text truncated to 300 characters per failure
- Chronological ordering within each project group

---

## Use Cases

1. **Daily review** - Check what failed in your sessions today
2. **Project investigation** - See all failures for a specific project in one day
3. **Trend analysis** - Compare reports across days to identify patterns
4. **Debugging** - Quickly find error messages and their context
5. **Performance tracking** - Monitor if error rates are improving
6. **Incident response** - Understand timeline of errors on a specific day

---

## Data Fields Included

For each failed tool call:
- **Time** - When the call failed (HH:MM:SS)
- **Tool** - Which tool was called (Bash, Edit, Read, etc.)
- **Error Type** - Classification (exit_code, validation, timeout, etc.)
- **Session** - Session ID (first 8 chars shown in table)
- **Project** - Which project the failure occurred in
- **Error Text** - Full error message with context
- **Error Class** - Binary: exit_code, token_limit, validation, permission, timeout, network, sibling_error, unknown_skill, other

---

## Notes

- Reports are generated fresh each time - no caching
- All historical failures are available in reports
- Run daily after sessions to keep reports current
- Can be integrated into automation/CI/CD pipelines
- Markdown format makes reports viewable in any editor or web interface
