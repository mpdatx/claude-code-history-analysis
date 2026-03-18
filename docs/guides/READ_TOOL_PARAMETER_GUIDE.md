# Read Tool Parameter Guide

## Common Error: offset/limit Type Mismatch

**Error Message**:
```
InputValidationError: Read failed due to the following issue:
The parameter `offset` type is expected as `number` but provided as `string`
```

This error appears **7+ times** in analysis and is 100% preventable.

---

## The Problem

When using the Read tool with `limit` and `offset` parameters, these **must be numbers**, not strings.

### ❌ WRONG (String values)
```python
# All of these are WRONG - they pass strings
Read(file_path="/path/to/file", limit: "100", offset: "0")
Read(file_path="/path/to/file", limit: "50", offset: "10")
Read(file_path="/path/to/file", offset: "0")
```

### ✅ CORRECT (Numeric values)
```python
# All of these are CORRECT - they use numbers
Read(file_path="/path/to/file", limit: 100, offset: 0)
Read(file_path="/path/to/file", limit: 50, offset: 10)
Read(file_path="/path/to/file", offset: 0)
```

---

## Why This Happens

Claude sometimes treats parameters as strings by default, especially when:
- Constructing parameters dynamically
- Copy-pasting from documentation that uses quoted examples
- Using parameters from text-based calculations
- Not thinking about parameter types

---

## Read Tool Reference

### Parameters
- **file_path** (required): string - absolute path to file
- **limit** (optional): **number** - lines to read (must be numeric!)
- **offset** (optional): **number** - line to start from (must be numeric!)

### Correct Usage Examples

```python
# Read first 100 lines
Read(file_path="/path/to/file.txt", limit: 100)

# Read 100 lines starting from line 50
Read(file_path="/path/to/file.txt", limit: 100, offset: 50)

# Read all after line 1000
Read(file_path="/path/to/file.txt", offset: 1000)

# Calculate offset, but use as number
start_line = 50
Read(file_path="/path/to/file.txt", offset: start_line)
```

---

## Prevention Checklist

Before calling Read tool, verify:
- [ ] `limit` is a number (no quotes: `100` not `"100"`)
- [ ] `offset` is a number (no quotes: `0` not `"0"`)
- [ ] file_path is a string (quotes OK here: `"/path/to/file"`)
- [ ] File exists (use Glob to verify first if unsure)

---

## Suggested CLAUDE.md Guideline

### Read Tool: Use Numeric limit/offset Parameters

**Rule**: When using Read tool's limit and offset parameters, they MUST be numbers, not strings

**Why**: The Read tool strictly validates parameter types. `limit: "100"` fails with InputValidationError, but `limit: 100` works.

**How to apply**:
- Always use `limit: 100` (not `limit: "100"`)
- Always use `offset: 0` (not `offset: "0"`)
- If calculating offset, store as number: `offset = 50` then use `offset: offset`
- String values for file_path are OK: `file_path: "/path/to/file.txt"`

**Prevents**: 7+ "offset type mismatch" errors

---

## Related Common Mistakes

### Also Check These Parameters

**Write Tool**:
```python
# ❌ WRONG - filename as parameter
Write(filename: "/path/to/file.txt", content: "text")

# ✅ CORRECT - file_path as parameter
Write(file_path: "/path/to/file.txt", content: "text")
```

**Edit Tool**:
```python
# ❌ WRONG - file_path as string
Edit(file_path: "/path/to/file.txt", old_string: "...", new_string: "...")

# ✅ CORRECT - file_path as Path object is also fine
Edit(file_path: Path("/path/to/file.txt"), old_string: "...", new_string: "...")
```

**Glob Tool**:
```python
# ❌ WRONG - might not work with some patterns
Glob(pattern: "src/**/*.txt")

# ✅ CORRECT - explicit pattern matching
Glob(pattern: "src/**/[0-9a-f]*.txt")
```

---

## Error Recovery

If you see this error:

1. **Read the error**: Identifies which parameter is wrong
2. **Check types**: Look at your limit/offset - remove quotes if present
3. **Fix**: Change `"100"` to `100` and retry once
4. **Test**: Use a simple command first: `Read(file_path: path, limit: 10)`

---

## Data from Analysis

**Occurrences**: 7 in daily failure reports
**Pattern**: Always `offset` parameter (sometimes `limit`)
**Root cause**: Parameter passed as string instead of number
**Prevention**: Simple guideline + checklist
**Impact**: 100% preventable

---

## Implementation Notes

This is a **parameter type validation** issue, not a logical issue. It's purely about how the parameter is passed.

The Read tool's validation is strict:
- `limit: 100` ✓ Valid
- `limit: "100"` ✗ Invalid
- `offset: 0` ✓ Valid
- `offset: "0"` ✗ Invalid

There's no workaround - you must use the correct type.

---

## Summary

**To avoid this error:**
1. Remember: `limit` and `offset` must be NUMBERS, not strings
2. Use `limit: 100` not `limit: "100"`
3. Use `offset: 0` not `offset: "0"`
4. Everything else (file_path) should be strings
5. Check before calling if unsure

**Impact if added to CLAUDE.md**: Eliminates 7+ errors
