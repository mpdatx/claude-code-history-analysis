"""Allow running as: python -m claude_history <subcommand>"""

import sys
from pathlib import Path

# Ensure repo root is on sys.path so tools/ imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.cli import app

app()
