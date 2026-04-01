# Search Command Design

Full-text regex search across all Claude Code session history, with results displayed as timeline-style session cards with match highlighting.

## CLI Interface

```
claude-history search <pattern> [--output FILE]
```

- **`pattern`** (required, positional): regex pattern (case-insensitive). Simple substrings work as-is.
- **`--output`**: override output file path.
- Respects global flags: `--project`, `--recent`, `--html/--no-html`.
- Default output: `output/search_<sanitized-pattern>.html` (or `.md`).
  - Pattern sanitized: non-alphanumeric chars replaced with `_`, truncated to 50 chars.

In interactive mode (`-i`), the user is prompted for the pattern after selecting the `search` command and project scope.

## Scanning & Matching

New `tools/search.py` with a `scan_sessions()` function.

### Process

1. Collect JSONL files via `find_history_files()` (respects `--project` / `--recent`).
2. For each file, iterate with `iter_jsonl()` (needs raw entry access for timestamps, git branch, version).
3. For each entry, extract all searchable text:
   - **User text messages** (after `strip_system_tags`)
   - **Assistant text messages**
   - **Tool use**: tool name + `json.dumps(input)`
   - **Tool results**: content string
4. Test compiled regex (`re.IGNORECASE`) against each piece of text.
5. Build a session dict for sessions with at least one match.

### Session Dict

Same fields as timeline's `parse_session()`:
- `id`, `file`, `start_time`, `end_time`
- `user_messages`, `assistant_messages`
- `tools_used` (Counter), `tool_errors`
- `git_branch`, `version`
- `messages` (all events, for full card context)

Plus search-specific fields:
- `match_count`: total matches in this session
- Per-event `matched: bool` and `match_spans: list[(start, end)]` for highlighting (spans are relative to the display text stored in the event's `text` field, not the raw JSONL)

Every session gets all its events parsed (for the full card display), and each event is tagged with whether it matched and where.

## HTML Output

Uses `html_theme.py` base CSS plus search-specific styles.

### Page Structure

**Header:** "Search: `<pattern>`" with subtitle showing date range and generation time.

**Stats grid (search-oriented):**
- Total matches (individual match occurrences)
- Sessions with matches (of total scanned)
- Projects with matches
- Matches in user messages
- Matches in assistant messages
- Matches in tool calls/results

**Heatmap:** Matches per day (not messages per day).

**Session cards:** Same visual structure as timeline:
- Clickable to expand, showing date, duration, branch, message counts, tool tags.
- Match count badge on the card header (e.g., "12 matches").
- All events shown (full session context).
- Matched text highlighted with `<mark>` elements using a distinct background (`rgba(210, 153, 34, 0.3)` background + border) visible on the dark theme.

**Filter bar:** Client-side text filter across visible cards (same as timeline).

**JavaScript:**
- UTC-to-local time conversion (same as timeline).
- "Jump to next match" button per card that scrolls to the next `<mark>` within the expanded detail.

### Highlight CSS

```css
mark {
    background: rgba(210, 153, 34, 0.3);
    color: var(--text);
    padding: 1px 3px;
    border-radius: 3px;
    border-bottom: 2px solid var(--orange);
}
```

## Markdown/Terminal Output (`--no-html`)

Grouped by session:

```
## Search: "pattern" -- 42 matches across 8 sessions in 3 projects

### Session: 2026-03-21 14:30 (my-project) -- 5 matches
  [USER]        matched text with **pattern** bolded...
  [ASSISTANT]   some response containing **pattern**...
  [TOOL_USE]    Bash: command with **pattern**...

### Session: 2026-03-20 09:15 (other-project) -- 3 matches
  ...
```

- Match highlighting uses `**bold**` markers around matched text.
- Only matching events shown (not full session) since terminal output should be scannable.
- Summary line at top with total counts.

## File Changes

### New file

- `tools/search.py` -- `scan_sessions()`, `generate_html()`, `generate_markdown()`

### Modified file

- `tools/cli.py` -- new `search` subcommand (~30 lines, same pattern as `timeline`)

### No changes to library

The existing `claude_history/` package provides all needed utilities:
- `parsing.find_history_files`, `parsing.iter_jsonl`
- `filters.strip_system_tags`, `filters.extract_user_text`
- `timestamps.parse_timestamp`, `timestamps.format_duration`
- `html_theme.get_base_css`
