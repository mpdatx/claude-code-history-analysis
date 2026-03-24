"""Shared dark-theme CSS for all HTML reports."""


def get_base_css() -> str:
    """Return the shared dark-theme CSS used by all HTML reports."""
    return """
:root {
    --bg: #0d1117;
    --surface: #161b22;
    --surface2: #1c2129;
    --border: #30363d;
    --text: #e6edf3;
    --text2: #8b949e;
    --accent: #58a6ff;
    --accent2: #388bfd;
    --green: #3fb950;
    --red: #f85149;
    --orange: #d29922;
    --purple: #bc8cff;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.5;
}
.container { max-width: 1200px; margin: 0 auto; padding: 24px 20px; }
.header {
    text-align: center;
    padding: 40px 20px 30px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 30px;
}
.header h1 { font-size: 28px; font-weight: 600; margin-bottom: 6px; }
.header .subtitle { color: var(--text2); font-size: 15px; }
.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 14px;
    margin-bottom: 30px;
}
.stat-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 18px;
    text-align: center;
}
.stat-card .stat-value { font-size: 28px; font-weight: 700; color: var(--accent); }
.stat-card .stat-label { font-size: 12px; color: var(--text2); text-transform: uppercase; letter-spacing: 0.5px; margin-top: 2px; }
table {
    width: 100%;
    border-collapse: collapse;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
    margin-bottom: 20px;
}
th {
    background: var(--surface2);
    padding: 10px 14px;
    text-align: left;
    font-size: 12px;
    color: var(--text2);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-bottom: 1px solid var(--border);
}
td {
    padding: 8px 14px;
    font-size: 14px;
    border-bottom: 1px solid var(--border);
}
tr:last-child td { border-bottom: none; }
tr:hover { background: var(--surface2); }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.filter-bar { margin-bottom: 16px; }
.filter-bar input {
    width: 100%;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 14px;
    color: var(--text);
    font-size: 14px;
    outline: none;
}
.filter-bar input:focus { border-color: var(--accent); }
.filter-bar input::placeholder { color: var(--text2); }
details { margin-bottom: 12px; }
summary {
    cursor: pointer;
    padding: 10px 14px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    font-weight: 600;
    color: var(--text);
}
summary:hover { border-color: var(--accent); }
details[open] summary { border-radius: 8px 8px 0 0; margin-bottom: 0; }
details .detail-content { padding: 14px; background: var(--surface); border: 1px solid var(--border); border-top: none; border-radius: 0 0 8px 8px; }
pre {
    background: var(--surface2);
    padding: 12px;
    border-radius: 6px;
    overflow-x: auto;
    font-size: 13px;
    color: var(--text2);
    margin: 8px 0;
}
.section { margin-bottom: 30px; }
.section-title { font-size: 18px; font-weight: 600; margin-bottom: 14px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
"""
