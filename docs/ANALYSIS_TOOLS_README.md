# Claude History Analysis Tools

Two comprehensive analysis tools for understanding patterns in Claude Code history files.

## Overview

| Tool | Purpose | Focus | Output |
|------|---------|-------|--------|
| `python tools/cli.py analyze` | Broad pattern analysis | Tool usage patterns, retries, suboptimal calls | `claude_history_report_*.md` |
| `python tools/cli.py failures` | Deep error analysis | Tool failures, error classification, root causes | `claude_tool_failures_*.md` |

Alternatively, use `python -m claude_history` as the module entry point.

## Tool 1: analyze (broad pattern analysis)

**Purpose**: Identify broad patterns in Claude Code usage across all sessions.

### What it detects:

- **D1: Tool Call Errors**
  - Grouped by error type: exit_code, token_limit, validation, other
  - Helps identify systematic issues with tool usage

- **D2: Permission Denials**
  - Tools that are frequently denied access
  - Auto-generates `settings.json` suggestions for top denied tools

- **D3: Repeated Retries**
  - Same tool called 3+ times in quick succession
  - Indicates debugging loops or inefficient approaches

- **D4: Suboptimal Tool Use**
  - Using Bash for `ls`, `grep`, `find`, `cat`, `head`, `tail`
  - Recommends dedicated tools: Glob, Grep, Read

### Usage:

```bash
python tools/cli.py analyze                           # Auto-detect projects
python tools/cli.py analyze --projects-dir PATH      # Scoped analysis
python tools/cli.py analyze --output report.md       # Custom output

# Alternative module invocation
python -m claude_history analyze
```

### Output:

- Terminal summary table with category counts
- Markdown report with 4 sections (D1-D4)
- Guidelines for each category
- Real examples from history

---

## Tool 2: failures (deep error analysis)

**Purpose**: Deep dive into tool errors - classification, patterns, and root cause analysis.

### What it provides:

1. **Executive Summary**
   - Total errors found and tools affected
   - Scope: projects and sessions involved

2. **Top Offending Tools**
   - Ranked by error count
   - Shows projects and sessions affected
   - Bash: the majority of all errors
   - Edit: a frequent source of errors
   - Read: another significant source

3. **Error Distribution by Category**
   - Exit code: the most common category
   - Permission: a significant portion
   - Validation: a smaller but preventable category
   - Network: occasional occurrences
   - Others: various

4. **Detailed Per-Tool Analysis**
   - Error type breakdown for each tool
   - Recent error examples with full context
   - Exit code distribution (for Bash)

5. **Tool-Specific Recommendations**
   - Bash: Suggest command breaking, error checking
   - Edit: Verify string matching, use Read first
   - Read: Handle large files with limit/offset
   - Write: Check parent directories exist
   - Others: Tool-specific guidance

6. **Common Error Patterns**
   - Most frequently occurring error messages
   - Shows frequency of each pattern

7. **Error Statistics**
   - Projects with most errors
   - Session-level analysis
   - Helps identify problematic projects

### Usage:

```bash
python tools/cli.py failures                           # Full analysis
python tools/cli.py failures --projects-dir PATH      # Scoped analysis
python tools/cli.py failures --output failures.md     # Custom output

# Alternative module invocation
python -m claude_history failures
```

### Output:

- Detailed markdown report
- Comprehensive tool-by-tool breakdown
- Actionable recommendations
- Error pattern analysis
- Project-level statistics

---

## Key Findings (From Analysis)

### Bash Dominates Errors
- Bash is the most common source of tool errors — the majority of all failures
- Exit code 1 is the single most frequent error pattern
- Exit code 127 (command not found) is another common source

### Permission Issues
- Permission denied errors are a significant category
- Read tool and Bash are the most frequently blocked tools

### Edit Tool Problems
- "File has not been read yet" is the most common Edit error
- Invalid string matching is the second most common cause

### Pattern Insights
- "Exit code 1" is the most frequent error message
- "Permission denied" and "File not found" are also common
- Sibling tool failures cascade from the above

---

## Recommendations

1. **Break Complex Bash Commands**
   - Exit code 1 is the most common error
   - Split into smaller commands with error checking
   - Use `set -e` or explicit error handlers

2. **Fix Edit Tool Usage**
   - Always use Read first to verify content
   - Ensure old_string matches exactly (whitespace matters)
   - Use `replace_all` parameter for ambiguous matches

3. **Handle Large Files**
   - Read token limit errors occur for large files
   - Use limit/offset parameters for large files
   - Consider reading in sections

4. **Permission Management**
   - Review settings.json — many denials detected
   - Consider allowing Read and Bash globally
   - Use project-specific overrides for tool-specific permissions

5. **Use Dedicated Tools**
   - Don't use Bash for file operations
   - Many suboptimal tool usages found
   - Use Glob (file discovery), Grep (search), Read (file reading)

---

## Report Files

Generated in the project directory:

- `claude_history_report_YYYY-MM-DD.md` — broad pattern analysis
- `claude_tool_failures_YYYY-MM-DD.md` — detailed error deep-dive

Both regenerate with current date when scripts are run.

---

## Technical Details

### Architecture

Both tools:
- Auto-detect `~/.claude/projects/` directory
- Glob pattern: `**/[0-9a-f]*-[0-9a-f]*.jsonl` (session files)
- Stream line-by-line with json.loads() for memory efficiency
- Track tool_use_id → tool name mapping
- Support scoped analysis with `--projects-dir`

### Error Classification

The failures tool uses regex-based classification:

- **exit_code**: `Exit code \d+`
- **token_limit**: "exceeds maximum allowed tokens"
- **validation**: "inputvalidationerror"
- **timeout**: "timeout" or "timed out"
- **permission**: "permission" or "denied"
- **not_found**: "not found" or "no such"
- **network**: "network", "request failed", or "http"
- **sibling_error**: "sibling tool call errored"
- **unknown_skill**: "unknown skill"
- **other**: anything else

### Data Sources

- Session files from `~/.claude/projects/`
- Multiple projects and sessions
- Streaming parser — handles large history sizes
- All tool errors across all sessions analyzed

---

## Extending the Analysis

Both tools are designed to be extended:

- Add new error categories in `ErrorCategory` enum
- Modify classification logic in `classify_error()`
- Add new detection patterns in `scan_history_files()`
- Customize recommendations in report generation functions

---

## Performance

- Streams session files efficiently
- Generates report quickly after scan
- Memory efficient: streaming parsing, no full file loading
- Suitable for large histories

---

## What's Different

### analyze (broad patterns)
- Focuses on PATTERNS
- 4 detection categories (D1-D4)
- Broader scope
- Includes retry analysis and suboptimal tool detection
- Shows settings.json suggestions

### failures (deep error analysis)
- Focuses on ROOT CAUSES
- Deep error classification
- Detailed per-tool analysis
- Exit code distribution
- Common error pattern extraction
- Tool-specific recommendations
- Project-level statistics
- Longer, more detailed report

Use both together for complete understanding:
1. Run `python tools/cli.py analyze` for patterns overview
2. Run `python tools/cli.py failures` for error deep-dive
3. Cross-reference findings for actionable improvements
